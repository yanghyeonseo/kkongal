"""AI 선별 오케스트레이션 — Django ORM 을 직접 사용(HTTP 왕복 없음).

파이프라인상 위치: crawl_notices → **classify_notices** → dispatch_alerts.
수집된 Notice 를, 그 출처를 구독한 사용자들의 관심 조건과 대조(LLM 또는 폴백)하여
평가한 모든 (공지,사용자) 쌍을 InboxNotice 로 저장하고, 점수와 함께
`is_recommended = (relevance_score >= 임계값)` 을 기록한다. 대시보드 '전체 공지'는
모든 행을, 'AI 추천' 탭·모든 알림은 `is_recommended=True` 행만 사용한다.
`notified_at` 은 알림 계층 소유이므로 절대 건드리지 않는다.

AI 가 최종 권위(authoritative)다: 크롤러의 순진한 키워드 매처(crawler/matcher.py)가
남기는 플레이스홀더 행과, LLM 장애 시의 결정론적 키워드 폴백 행은 아직 '확정 전'으로 보고
LLM 이 살아나면 다시 판정해 덮어쓴다. 반면 이미 LLM 으로 판정이 끝난
(`classified_by_llm=True`) (공지,사용자) 쌍은 비용 절감을 위해 `reclassify` 없이는 다시
호출하지 않는다(NFR-6).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Optional

from django.conf import settings

from account.models import Interest, ProfileAttribute
from notices.models import InboxNotice, Notice
from sources.models import SourceSubscription

from .llm import PROVIDER_LLM, LLMClient, get_client

logger = logging.getLogger("ai")

# crawler/matcher.py 가 크롤링 시점에 남기는 '순진한 키워드 매칭' 플레이스홀더의 reason 값.
# 재판정 여부는 이제 classified_by_llm(순진한 매처·폴백 행은 False → 재판정)로 판단하므로,
# 이 상수는 표시/참조·테스트용으로만 남긴다.
NAIVE_REASON = "Keyword match"

# merge 시 합산할 카운터 필드(집계 전용 notices_processed 는 run 단에서 증가)
_COUNTER_FIELDS = (
    "candidates",
    "created",
    "updated",
    "recommended",
    "below_threshold",
    "downgraded",
    "skipped_existing",
    "errors",
    "llm_calls",
    "fallback_calls",
)


@dataclass
class RunSummary:
    """분류 실행 결과 집계."""

    notices_processed: int = 0
    candidates: int = 0  # 실제 분류를 시도한 (공지,사용자) 쌍 수
    created: int = 0
    updated: int = 0  # 갱신/덮어쓴 InboxNotice(순진한 매처 행 override 포함)
    recommended: int = 0  # 이번 실행에서 is_recommended=True 로 판정한 쌍 수(추천 수)
    below_threshold: int = 0  # 임계값 미만(is_recommended=False)으로 저장한 쌍 수
    downgraded: int = 0  # 재판정에서 is_recommended 가 True→False 로 뒤집힌 행 수(삭제 안 함)
    skipped_existing: int = 0  # 이미 'AI' 로 분류된 쌍이라 LLM 호출 생략(NFR-6)
    errors: int = 0
    llm_calls: int = 0
    fallback_calls: int = 0

    def merge(self, other: "RunSummary") -> None:
        for name in _COUNTER_FIELDS:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    @property
    def provider(self) -> str:
        """이번 실행에서 사용된 판정 경로: llm / fallback / mixed / none."""
        if self.llm_calls and self.fallback_calls:
            return "mixed"
        if self.llm_calls:
            return PROVIDER_LLM
        if self.fallback_calls:
            return "fallback"
        return "none"

    def as_dict(self) -> dict[str, object]:
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["provider"] = self.provider
        return data


def _interest_payload(user) -> list[dict[str, object]]:
    """사용자의 관심 조건을 우선순위 내림차순으로 반환.

    Interest 모델에는 활성(active) 플래그가 없으므로 등록된 관심 조건 전량을 사용한다.
    """
    interests = Interest.objects.filter(user_id=user).order_by(
        "-priority", "-created_at"
    )
    return [
        {
            "keyword": interest.keyword,
            "description": interest.description,
            "priority": interest.priority,
        }
        for interest in interests
    ]


def _classify_pair(
    notice: Notice,
    user,
    *,
    client: LLMClient,
    threshold: float,
    reclassify: bool,
    dry_run: bool,
    existing_classified_by_llm: bool,
    summary: RunSummary,
) -> None:
    """(공지, 사용자) 한 쌍을 판정해 ``summary`` 를 갱신한다(inbox upsert).

    ``classify_notice`` 와 ``classify_notices_for_user`` 가 공유하는 단일 판정 단위.
    동작 규칙은 ``classify_notice`` 문서와 동일하다:
    - 이미 LLM 으로 분류된 쌍은 ``reclassify=False`` 면 LLM 호출 없이 생략(NFR-6).
      순진한 매처·폴백 행(``classified_by_llm=False``)은 생략 대상이 아니라 덮어쓰기 대상.
    - 평가한 쌍은 점수와 무관하게 항상 upsert(멱등)하고,
      ``is_recommended = (score >= threshold)`` 를 함께 저장한다(임계값 미만도 삭제하지
      않고 is_recommended=False 로 남긴다).
    - ``notified_at`` 은 절대 건드리지 않는다.
    - 개별 실패는 삼켜서 ``summary.errors`` 로만 집계한다(상위 루프 비중단).

    ``existing_classified_by_llm`` 은 ``reclassify=False`` 일 때 이 쌍의 기존 InboxNotice
    가 LLM 으로 확정됐는지(없으면 False). ``reclassify=True`` 면 무시된다.
    """

    if not reclassify and existing_classified_by_llm:
        # 이미 LLM 으로 분류가 끝난 쌍 → 비용 절약을 위해 재호출 생략(NFR-6).
        summary.skipped_existing += 1
        return

    try:
        interests = _interest_payload(user)
        if not interests:
            # 등록된 관심 조건이 없으면 매칭할 대상이 없다.
            return

        summary.candidates += 1
        # Category 2(사용자 지정) 커스텀 필드 — label/value 쌍 목록. 도메인마다 다르므로
        # 고정 필드와 분리해 프롬프트의 '추가 정보' 섹션으로 렌더한다.
        attributes = list(
            ProfileAttribute.objects.filter(user_id=user).values("label", "value")
        )
        verdict = client.classify(
            title=notice.title,
            content=notice.content,
            publisher=notice.publisher,
            profile={
                "age": user.age,
                "gender": user.gender,
                "region": user.region,
                "job": user.job,
                "bio": user.bio,
                "attributes": attributes,
            },
            interests=interests,
            # 보강 단계에서 만든 3문장 요약이 있으면 함께 실어 판단 품질↑·비용↓.
            summary=notice.summary,
        )

        if verdict.provider == PROVIDER_LLM:
            summary.llm_calls += 1
        else:
            summary.fallback_calls += 1

        is_recommended = verdict.score >= threshold
        if is_recommended:
            summary.recommended += 1
        else:
            summary.below_threshold += 1

        if dry_run:
            exists = InboxNotice.objects.filter(
                user_id=user, notice_id=notice
            ).exists()
            if exists:
                summary.updated += 1
            else:
                summary.created += 1
            return

        # 재판정에서 추천→비추천으로 뒤집힌 행을 집계(삭제하지 않고 값만 갱신).
        if not is_recommended and InboxNotice.objects.filter(
            user_id=user, notice_id=notice, is_recommended=True
        ).exists():
            summary.downgraded += 1

        # 점수와 무관하게 항상 저장한다: '전체 공지'는 모든 행을, 'AI 추천'·알림은
        # is_recommended=True 행만 쓴다. update_or_create 는 notified_at 을 defaults 에
        # 넣지 않으므로 절대 안 건드린다.
        _, created = InboxNotice.objects.update_or_create(
            user_id=user,
            notice_id=notice,
            defaults={
                "relevance_score": verdict.score,
                "matched_keywords": ", ".join(verdict.matched_keywords),
                "reason": verdict.reason,
                "is_recommended": is_recommended,
                # LLM 이 실제로 판정했을 때만 '확정'으로 표시. 폴백이면 False → 다음 실행에서
                # LLM 이 살아나면 다시 판정한다(폴백 고착 방지).
                "classified_by_llm": verdict.provider == PROVIDER_LLM,
            },
        )
        if created:
            summary.created += 1
        else:
            summary.updated += 1
    except Exception:  # 한 사용자 실패가 전체를 막지 않도록
        logger.exception("분류 실패 (notice=%s, user=%s)", notice.id, user.id)
        summary.errors += 1


def classify_notice(
    notice: Notice,
    *,
    client: Optional[LLMClient] = None,
    reclassify: bool = False,
    threshold: Optional[float] = None,
    dry_run: bool = False,
) -> RunSummary:
    """한 공지를, 그 출처를 구독한 사용자들의 관심 조건과 대조해 inbox 를 채운다.

    - 평가한 모든 쌍을 InboxNotice 로 upsert(update_or_create) → 멱등. 점수와 함께
      `is_recommended = (score >= 임계값)` 를 저장한다. 임계값 미만도 삭제하지 않고
      is_recommended=False 로 남겨 '전체 공지'에 보이게 한다('AI 추천'·알림만 True 사용).
      순진한 매처가 남긴 'Keyword match' 행이 있으면 실제 점수/사유/키워드로 덮어쓴다
      (AI 가 최종 권위).
    - 이미 LLM 으로 분류된 (공지,사용자) 쌍은 `reclassify=False` 면 LLM 호출 없이 생략
      (NFR-6). 순진한 매처·폴백 행(classified_by_llm=False)은 재판정/덮어쓰기 대상.
    - `notified_at` 은 절대 건드리지 않는다(알림 계층 소유).
    - 개별 사용자 처리 실패가 전체 실행을 중단시키지 않는다.
    """

    client = client or get_client()
    threshold = (
        settings.LLM_RELEVANCE_THRESHOLD if threshold is None else threshold
    )
    summary = RunSummary()

    subscriptions = SourceSubscription.objects.filter(
        source_id_id=notice.source_id_id
    ).select_related("user_id")

    # (공지,사용자) 쌍은 유니크 → user_id 당 기존 행은 최대 1개.
    # classified_by_llm 로 'LLM 확정'(생략 대상)과 순진한 매처·폴백 행(덮어쓰기 대상)을 구분.
    existing_llm_by_user: dict[int, bool] = {}
    if not reclassify:
        existing_llm_by_user = dict(
            InboxNotice.objects.filter(notice_id=notice).values_list(
                "user_id", "classified_by_llm"
            )
        )

    for subscription in subscriptions:
        user = subscription.user_id
        # 행이 없거나 순진한 매처·폴백 행(classified_by_llm=False)이면 _classify_pair 가
        # 계속 진행해 덮어쓴다. 이미 LLM 으로 분류된 쌍이면 생략(NFR-6).
        _classify_pair(
            notice,
            user,
            client=client,
            threshold=threshold,
            reclassify=reclassify,
            dry_run=dry_run,
            existing_classified_by_llm=existing_llm_by_user.get(user.id, False),
            summary=summary,
        )

    logger.debug(
        "classify_notice(notice=%s): %s", notice.id, summary.as_dict()
    )
    return summary


def run_classification(
    *,
    since: Optional[datetime] = None,
    limit: Optional[int] = None,
    source_id: Optional[int] = None,
    reclassify: bool = False,
    threshold: Optional[float] = None,
    dry_run: bool = False,
    client: Optional[LLMClient] = None,
) -> RunSummary:
    """후보 공지들을 순회하며 분류한다.

    기본 후보군(NFR-6): 아직 LLM 으로 확정되지 않은 공지 — 행이 아예 없거나, 순진한
    매처·폴백 행만(classified_by_llm=False) 있는 공지. 순진한 매칭이 공지를 선점(shadow)해
    AI 선별을 막던 문제를 없애고, LLM 장애 중 남은 폴백 행도 LLM 복구 시 다시 판정하되,
    이미 LLM 이 확정한 공지는 재호출하지 않는다. `since` 를 주면 해당 시각 이후 생성 공지로
    한정하고, `reclassify=True` 면 이미 분류된 쌍까지 다시 판정한다.
    """

    client = client or get_client()
    total = RunSummary()

    notices = Notice.objects.all()
    if source_id is not None:
        notices = notices.filter(source_id_id=source_id)
    if since is not None:
        notices = notices.filter(created_at__gte=since)
    if not reclassify and since is None:
        # LLM 이 확정한(classified_by_llm=True) 행이 있는 공지만 후보에서 제외한다.
        # 순진한 매처·폴백 행만 있거나 행이 없는 공지는 LLM 이 살아나면 품질을 끌어올리도록
        # 후보로 남긴다(폴백 고착 방지). NOT EXISTS 서브쿼리라 전체 id 집합을 메모리에
        # 올리지 않는다.
        notices = notices.exclude(inbox_entries__classified_by_llm=True)
    notices = notices.select_related("source_id").order_by("-created_at", "-id")
    if limit is not None:
        notices = notices[:limit]

    for notice in notices:
        try:
            result = classify_notice(
                notice,
                client=client,
                reclassify=reclassify,
                threshold=threshold,
                dry_run=dry_run,
            )
        except Exception:  # 한 공지 실패가 전체 실행을 막지 않도록
            logger.exception("공지 분류 중 예외 (notice=%s)", notice.id)
            total.errors += 1
            continue
        total.notices_processed += 1
        total.merge(result)

    logger.info(
        "run_classification 완료: %s (provider=%s)",
        total.as_dict(),
        total.provider,
    )
    return total


def classify_notices_for_user(
    user,
    notices,
    *,
    reclassify: bool = False,
    threshold: Optional[float] = None,
    dry_run: bool = False,
    client: Optional[LLMClient] = None,
) -> dict[str, object]:
    """주어진 공지들을 **한 명의 사용자**에 대해서만 선별한다(온디맨드 동기화용).

    ``run_classification`` 이 (공지 → 그 출처의 모든 구독자) 를 도는 것과 달리, 이 헬퍼는
    (주어진 공지들 → 이 사용자 하나) 만 판정한다. 덕분에 사이트별 '동기화' 버튼처럼
    요청 사용자·소수 공지(≤10)만 처리해 LLM 비용을 최소화한다.

    - 평가한 모든 쌍을 InboxNotice 로 upsert(멱등)하고 is_recommended 를 함께 저장한다
      (임계값 미만도 삭제하지 않고 is_recommended=False 로 남긴다).
    - 이미 'AI' 로 분류된 (공지,이 사용자) 쌍은 ``reclassify=False`` 면 생략(NFR-6).
    - ``notified_at`` 은 절대 건드리지 않는다(알림 계층 소유).
    - 다른 사용자의 InboxNotice 는 절대 만들지/건드리지 않는다.

    반환: ``RunSummary.as_dict()`` (created 가 '새로 저장된' 쌍 수).
    """

    client = client or get_client()
    threshold = (
        settings.LLM_RELEVANCE_THRESHOLD if threshold is None else threshold
    )
    total = RunSummary()
    notices = list(notices)

    # 이 사용자에 한해, 대상 공지들의 'LLM 확정' 여부를 한 번에 읽어 NFR-6 생략에 쓴다.
    existing_llm_by_notice: dict[int, bool] = {}
    if not reclassify and notices:
        existing_llm_by_notice = dict(
            InboxNotice.objects.filter(
                user_id=user, notice_id__in=[n.id for n in notices]
            ).values_list("notice_id", "classified_by_llm")
        )

    for notice in notices:
        _classify_pair(
            notice,
            user,
            client=client,
            threshold=threshold,
            reclassify=reclassify,
            dry_run=dry_run,
            existing_classified_by_llm=existing_llm_by_notice.get(notice.id, False),
            summary=total,
        )
        total.notices_processed += 1

    logger.info(
        "classify_notices_for_user(user=%s): %s", user.id, total.as_dict()
    )
    return total.as_dict()
