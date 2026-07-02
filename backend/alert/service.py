"""알림 디스패치 오케스트레이션.

파이프라인의 마지막 단계: ``notified_at`` 이 비어 있고 관련도가 임계값 이상인
``InboxNotice`` 를 찾아, 각 사용자의 활성 알림 채널로 발송하고 ``AlertLog`` 를
기록한 뒤 ``notified_at`` 을 갱신해 중복 발송을 막는다.

견고성(NFR-3): 한 채널/사용자의 실패가 전체 루프를 중단시키지 않는다 —
모든 발송 시도를 try/except 로 감싼다.
"""

from __future__ import annotations

import logging
from collections import OrderedDict

from django.conf import settings
from django.utils import timezone

from notices.models import InboxNotice

from .models import AlertChannel, AlertLog
from .senders import alert_item_from_inbox, get_sender

logger = logging.getLogger("alert")


def _pending_queryset(user=None, limit=None):
    """발송 대상(미발송 + 임계값 이상) InboxNotice 쿼리셋."""

    threshold = settings.LLM_RELEVANCE_THRESHOLD
    queryset = (
        InboxNotice.objects.filter(
            notified_at__isnull=True,
            relevance_score__gte=threshold,
        )
        .select_related("notice_id", "notice_id__source_id", "user_id")
        .order_by("user_id_id", "-relevance_score", "-created_at", "id")
    )
    if user is not None:
        queryset = queryset.filter(user_id=user)
    if limit:
        queryset = queryset[:limit]
    return queryset


def _group_by_user(pending):
    """미발송 InboxNotice 목록을 사용자별로 묶는다 → {user_id: (user, [inbox, ...])}."""

    grouped: "OrderedDict[int, tuple[object, list]]" = OrderedDict()
    for inbox in pending:
        uid = inbox.user_id_id
        if uid not in grouped:
            grouped[uid] = (inbox.user_id, [])
        grouped[uid][1].append(inbox)
    return grouped


def dispatch_pending(user=None, limit=None) -> dict:
    """미발송 inbox 공지를 각 사용자의 활성 채널로 발송한다.

    Args:
        user: 특정 사용자에게만 발송하려면 지정(User 인스턴스). 기본은 전체.
        limit: 처리할 미발송 inbox 공지 최대 개수(선택).

    Returns:
        요약 dict — ``attempted``/``sent``/``failed`` 는 (사용자×채널) 발송 시도
        단위 집계이며, ``users_notified`` 는 최소 한 채널이라도 시도된 사용자 수.
    """

    summary = {"attempted": 0, "sent": 0, "failed": 0, "users_notified": 0}

    pending = list(_pending_queryset(user=user, limit=limit))
    if not pending:
        logger.info("dispatch_pending: 발송 대상 없음")
        return summary

    grouped = _group_by_user(pending)
    logger.info(
        "dispatch_pending: 미발송 %d건 / 사용자 %d명 처리 시작",
        len(pending),
        len(grouped),
    )

    for user_obj, inbox_notices in grouped.values():
        channels = list(
            AlertChannel.objects.filter(user_id=user_obj, is_active=True).order_by("id")
        )
        if not channels:
            # 활성 채널이 없으면 notified_at 을 건드리지 않고 건너뛴다(다음 기회에 재시도).
            logger.info(
                "사용자 %s: 활성 알림 채널 없음 → 건너뜀 (%d건 보류)",
                user_obj,
                len(inbox_notices),
            )
            continue

        items = [alert_item_from_inbox(inbox) for inbox in inbox_notices]
        attempted_any = False

        for channel in channels:
            summary["attempted"] += 1
            attempted_any = True
            ok, error = _send_via_channel(channel, items, user_obj)
            _record_logs(inbox_notices, channel, ok, error)
            if ok:
                summary["sent"] += 1
                logger.info(
                    "발송 성공: 사용자=%s 채널=%s(%s) 공지=%d건",
                    user_obj,
                    channel.id,
                    channel.type,
                    len(inbox_notices),
                )
            else:
                summary["failed"] += 1
                logger.warning(
                    "발송 실패: 사용자=%s 채널=%s(%s) 오류=%s",
                    user_obj,
                    channel.id,
                    channel.type,
                    error,
                )

        # 한 채널이라도 시도했으면 중복 방지를 위해 notified_at 을 갱신한다
        # (일부 채널이 실패했더라도 재발송 폭주를 막기 위함).
        if attempted_any:
            InboxNotice.objects.filter(
                id__in=[inbox.id for inbox in inbox_notices]
            ).update(notified_at=timezone.now())
            summary["users_notified"] += 1

    logger.info("dispatch_pending 완료: %s", summary)
    return summary


def _send_via_channel(channel, items, user_obj) -> tuple[bool, str]:
    """단일 채널 발송. 어떤 예외도 호출자에게 전파하지 않는다(NFR-3)."""

    sender = get_sender(channel)
    if sender is None:
        return False, f"지원하지 않는 채널 타입: {channel.type}"
    try:
        return sender.send(items, user_obj)
    except Exception as exc:  # noqa: BLE001 - 방어적: 발송기 내부 계약을 넘어선 예외까지 격리
        logger.exception("발송기 예외 (채널=%s, 타입=%s)", channel.id, channel.type)
        return False, f"예상치 못한 오류: {type(exc).__name__}: {exc}"


def _record_logs(inbox_notices, channel, ok, error) -> None:
    """대상 inbox 공지 각각에 대해 AlertLog 한 건씩 기록한다."""

    now = timezone.now()
    status = AlertLog.Status.SENT if ok else AlertLog.Status.FAILED
    logs = [
        AlertLog(
            inbox_notice_id=inbox,
            channel_id=channel,
            status=status,
            error="" if ok else (error or ""),
            sent_at=now if ok else None,
        )
        for inbox in inbox_notices
    ]
    AlertLog.objects.bulk_create(logs)
