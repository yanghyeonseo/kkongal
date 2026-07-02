"""AI 선별 오케스트레이션 — Django ORM 을 직접 사용(HTTP 왕복 없음).

파이프라인상 위치: crawl_notices → **classify_notices** → dispatch_alerts.
수집된 Notice 를, 그 출처를 구독한 사용자들의 관심 조건과 대조(LLM 또는 폴백)하여
임계값 이상이면 InboxNotice 로 upsert 한다. `notified_at` 은 알림 계층 소유이므로
절대 건드리지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Optional

from django.conf import settings

from account.models import Interest
from notices.models import InboxNotice, Notice
from sources.models import SourceSubscription

from .llm import PROVIDER_LLM, LLMClient, get_client

logger = logging.getLogger("ai")

# merge 시 합산할 카운터 필드(집계 전용 notices_processed 는 run 단에서 증가)
_COUNTER_FIELDS = (
    "candidates",
    "created",
    "updated",
    "below_threshold",
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
    created: int = 0  # 새로 만든 InboxNotice
    updated: int = 0  # 갱신한 InboxNotice
    below_threshold: int = 0  # 임계값 미만이라 제외
    skipped_existing: int = 0  # 이미 분류된 쌍이라 LLM 호출 생략(NFR-6)
    errors: int = 0
    llm_calls: int = 0  # 실제 LLM 경로로 판정한 횟수
    fallback_calls: int = 0  # 키워드 폴백으로 판정한 횟수

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


def classify_notice(
    notice: Notice,
    *,
    client: Optional[LLMClient] = None,
    reclassify: bool = False,
    threshold: Optional[float] = None,
    dry_run: bool = False,
) -> RunSummary:
    """한 공지를, 그 출처를 구독한 사용자들의 관심 조건과 대조해 inbox 를 채운다.

    - 임계값 이상만 InboxNotice 로 upsert(update_or_create) → 멱등.
    - 임계값 미만은 inbox 를 어지럽히지 않도록 건너뜀.
    - 이미 분류된 (공지,사용자) 쌍은 `reclassify=False` 면 LLM 호출 없이 생략(NFR-6).
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

    already_classified: set[int] = set()
    if not reclassify:
        already_classified = set(
            InboxNotice.objects.filter(notice_id=notice).values_list(
                "user_id", flat=True
            )
        )

    for subscription in subscriptions:
        user = subscription.user_id
        if not reclassify and user.id in already_classified:
            summary.skipped_existing += 1
            continue

        try:
            interests = _interest_payload(user)
            if not interests:
                # 활성 관심 조건이 없으면 매칭할 대상이 없다.
                continue

            summary.candidates += 1
            verdict = client.classify(
                title=notice.title,
                content=notice.content,
                publisher=notice.publisher,
                profile={
                    "age": user.age,
                    "job": user.job,
                    "gender": user.gender,
                },
                interests=interests,
            )

            if verdict.provider == PROVIDER_LLM:
                summary.llm_calls += 1
            else:
                summary.fallback_calls += 1

            if verdict.score < threshold:
                summary.below_threshold += 1
                continue

            if dry_run:
                exists = InboxNotice.objects.filter(
                    user_id=user, notice_id=notice
                ).exists()
                if exists:
                    summary.updated += 1
                else:
                    summary.created += 1
                continue

            _, created = InboxNotice.objects.update_or_create(
                user_id=user,
                notice_id=notice,
                defaults={
                    "relevance_score": verdict.score,
                    "matched_keywords": ", ".join(verdict.matched_keywords),
                    "reason": verdict.reason,
                },
            )
            if created:
                summary.created += 1
            else:
                summary.updated += 1
        except Exception:  # 한 사용자 실패가 전체를 막지 않도록
            logger.exception(
                "분류 실패 (notice=%s, user=%s)", notice.id, user.id
            )
            summary.errors += 1

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

    기본 후보군(NFR-6): 아직 아무에게도 분류되지 않은 공지만. `since` 를 주면 해당
    시각 이후 생성 공지로 한정하고, `reclassify=True` 면 이미 분류된 쌍까지 다시 판정.
    """

    client = client or get_client()
    total = RunSummary()

    notices = Notice.objects.all()
    if source_id is not None:
        notices = notices.filter(source_id_id=source_id)
    if since is not None:
        notices = notices.filter(created_at__gte=since)
    if not reclassify and since is None:
        # 한 번도 분류된 적 없는 신규 공지만 (LLM 호출 최소화).
        classified = InboxNotice.objects.values_list(
            "notice_id", flat=True
        ).distinct()
        notices = notices.exclude(id__in=classified)
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
