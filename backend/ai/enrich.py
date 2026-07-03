"""공지 보강(enrichment) — 공지당 1회, 사용자/관심사 무관.

파이프라인상 위치: crawl_notices → **enrich_notices** → classify_notices → dispatch.
크롤 직후 각 Notice 를 LLM **1회** 호출로 보강해 세 필드를 채운다:
- ``deadline_at``: 신청/마감 기한을 파싱해 aware datetime 으로 저장(없으면 null)
- ``summary``: 한국어 3문장 요약
- ``content_markdown``: 원문 정보를 보존한 깔끔한 markdown

안전 장치:
- **멱등**(NFR-6): 이미 LLM 으로 보강된(``enriched_by_llm``) 공지는 호출 없이 skip
  (``force`` 로 재보강). 폴백으로만 채운 공지는 skip 하지 않아 LLM 이 살아나면 재보강된다.
- 키 없음/호출 실패 시 오프라인 폴백(요약=본문 앞부분, markdown=원문, deadline=None).
- 어떤 경우에도 예외를 밖으로 던지지 않는다(개별 실패는 삼켜 카운트로만 집계).

보강은 사용자 무관이므로 recommendation(ai/service.py)과 완전히 분리된다.
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Optional

from dateutil import parser as date_parser
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from notices.models import Notice

from .llm import PROVIDER_LLM, LLMClient, first_sentences, get_client

logger = logging.getLogger("ai")

# LLM 이 마감 정보가 '없음'을 표현하는 흔한 값들 — 파싱 시도 없이 None 으로 본다.
_NULLISH = {
    "",
    "null",
    "none",
    "n/a",
    "na",
    "미상",
    "없음",
    "미정",
    "해당없음",
    "무관",
}


def _aware(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def parse_deadline(value: object) -> Optional[datetime]:
    """LLM 이 준 마감일 문자열을 aware datetime 으로 견고하게 파싱한다.

    ISO datetime → ISO date → dateutil fuzzy 순으로 시도하고, 실패하거나 '없음'류
    값이면 None. naive 결과는 현재 타임존 기준 aware 로 승격한다. 결코 예외를
    던지지 않는다(crawler.repository.parse_notice_datetime 과 같은 전략).
    """

    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _NULLISH:
        return None

    parsed_dt = parse_datetime(text)
    if parsed_dt:
        return _aware(parsed_dt)

    parsed_d = parse_date(text)
    if parsed_d:
        return _aware(datetime.combine(parsed_d, time.min))

    try:
        guessed = date_parser.parse(text, fuzzy=True)
    except (TypeError, ValueError, OverflowError):
        return None
    return _aware(guessed)


def enrich_notice(
    notice: Notice,
    *,
    client: Optional[LLMClient] = None,
    force: bool = False,
) -> dict:
    """한 공지를 보강해 summary/content_markdown/deadline_at 를 저장한다.

    - **멱등**: 이미 LLM 으로 보강됐고(``enriched_by_llm``) ``force=False`` 면 호출 없이 skip.
      폴백으로만 채운 공지는 skip 하지 않아 LLM 복구 시 재보강된다(폴백 고착 방지).
    - LLM **1회** 호출로 세 필드를 산출. 키 없음/실패 시 오프라인 폴백으로 저장.
    - ``notified_at`` 등 다른 계층 소유 필드는 건드리지 않는다(update_fields 로 한정).
    - 어떤 경우에도 예외를 밖으로 던지지 않는다.

    반환: ``{"status": "enriched"|"skipped"|"fallback"|"error", "provider": str,
    "deadline_at": bool, "notice_id": int|None}``.
    """

    notice_id = getattr(notice, "id", None)

    if not force and notice.enriched_by_llm:
        # 이미 LLM 으로 보강된 공지 → 비용 절약을 위해 재호출 생략(NFR-6).
        return {
            "status": "skipped",
            "provider": "none",
            "deadline_at": notice.deadline_at is not None,
            "notice_id": notice_id,
        }

    client = client or get_client()
    try:
        result = client.enrich(title=notice.title, content=notice.content)
        deadline = parse_deadline(result.deadline)

        notice.summary = result.summary
        notice.content_markdown = result.content_markdown
        # 보강이 마감일을 못 뽑아냈으면(LLM null / 폴백) 크롤러가 넣어 둔 기존
        # deadline_at 을 덮어써 지우지 않는다 — 있는 마감일을 보존한다.
        notice.deadline_at = deadline or notice.deadline_at
        # LLM 이 실제로 보강했을 때만 '완료'로 표시. 폴백이면 False 로 남겨 재보강 여지를 둔다.
        notice.enriched_by_llm = result.provider == PROVIDER_LLM
        notice.save(
            update_fields=[
                "summary",
                "content_markdown",
                "deadline_at",
                "enriched_by_llm",
                "updated_at",
            ]
        )

        status = "enriched" if result.provider == PROVIDER_LLM else "fallback"
        return {
            "status": status,
            "provider": result.provider,
            "deadline_at": deadline is not None,
            "notice_id": notice_id,
        }
    except Exception:  # 클라이언트는 폴백을 반환하지만, 저장/파싱 등 예기치 못한 실패까지 방어
        logger.exception("공지 보강 실패 (notice=%s)", notice_id)
        # 최후의 방어: 원문 기반 폴백으로라도 채워 둔다(그래도 실패하면 조용히 포기).
        try:
            text = (notice.content or "").strip()
            if not (notice.summary or "").strip():
                notice.summary = first_sentences(text, 3)
            if not (notice.content_markdown or "").strip():
                notice.content_markdown = text
            notice.save(
                update_fields=["summary", "content_markdown", "updated_at"]
            )
        except Exception:
            logger.exception("공지 보강 폴백 저장도 실패 (notice=%s)", notice_id)
        return {
            "status": "error",
            "provider": "none",
            "deadline_at": False,
            "notice_id": notice_id,
        }


def enrich_notices(
    notices,
    *,
    client: Optional[LLMClient] = None,
    force: bool = False,
) -> dict:
    """여러 공지를 보강한다(이미 보강된 것은 skip, NFR-6). 카운트 dict 반환.

    반환: ``{"processed", "enriched", "skipped", "fallback", "errors"}`` 카운트.
    하나의 클라이언트를 재사용해 배치 비용을 낮춘다.
    """

    client = client or get_client()
    counts = {
        "processed": 0,
        "enriched": 0,
        "skipped": 0,
        "fallback": 0,
        "errors": 0,
    }
    for notice in notices:
        counts["processed"] += 1
        result = enrich_notice(notice, client=client, force=force)
        status = result.get("status")
        if status == "enriched":
            counts["enriched"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status == "fallback":
            counts["fallback"] += 1
        else:
            counts["errors"] += 1

    logger.info("enrich_notices 완료: %s", counts)
    return counts
