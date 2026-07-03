"""알림 디스패치 오케스트레이션.

파이프라인의 마지막 단계: ``notified_at`` 이 비어 있고 ``is_recommended=True`` 인
``InboxNotice`` 를 찾아, 각 사용자의 활성 알림 채널로 발송하고 ``AlertLog`` 를
기록한 뒤 ``notified_at`` 을 갱신해 중복 발송을 막는다. AI 추천 여부의 판단
(관련도 임계값 비교)은 분류 단계(ai/service.py)가 소유하며 여기서는 그 결과인
``is_recommended`` 만 신뢰한다.

견고성(NFR-3):
  - 한 채널의 실패가 다른 채널 발송을 막지 않고,
  - 한 사용자의 예상치 못한 오류가 전체 루프를 중단시키지 않는다(사용자 단위 격리),
  - 한 채널이라도 성공해야 ``notified_at`` 을 갱신한다. 전 채널이 실패하면 미발송으로
    남겨 다음 주기에 재시도한다(일시적 장애로 인한 알림 유실 방지).
"""

from __future__ import annotations

import logging
from collections import OrderedDict

from django.db import transaction
from django.utils import timezone

from notices.models import InboxNotice

from .models import AlertChannel, AlertLog
from .senders import alert_item_from_inbox, get_sender

logger = logging.getLogger("alert")


def _pending_queryset(user=None, limit=None):
    """발송 대상(미발송 + AI 추천) InboxNotice 쿼리셋."""

    queryset = (
        InboxNotice.objects.filter(
            notified_at__isnull=True,
            is_recommended=True,
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
        요약 dict — ``attempted``/``sent``/``failed`` 는 (사용자×채널) 실제 발송
        시도 단위 집계이며, ``users_notified`` 는 실제로 발송을 시도한 사용자 수.
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
        # 사용자 단위 격리(NFR-3): 한 사용자 처리 중 예상치 못한 오류가 나도
        # 그 사용자만 건너뛰고(다음 기회에 재시도) 나머지 사용자 발송은 계속한다.
        try:
            _dispatch_for_user(user_obj, inbox_notices, summary)
        except Exception:  # noqa: BLE001 - 방어적: 사용자 단위로 오류 격리
            logger.exception("사용자 %s 처리 중 예상치 못한 오류 → 건너뜀", user_obj)

    logger.info("dispatch_pending 완료: %s", summary)
    return summary


def _dispatch_for_user(user_obj, inbox_notices, summary) -> None:
    """한 사용자의 미발송 공지를, 발송 가능한 활성 채널 각각으로 보낸다."""

    channels = AlertChannel.objects.filter(user_id=user_obj, is_active=True).order_by(
        "id"
    )
    # 실제 발송기가 있는 채널만 남긴다. kakao 등 미지원 타입(get_sender→None)만
    # 있으면 '활성 채널 없음' 과 동일하게 취급해 notified_at 을 건드리지 않는다
    # (그렇지 않으면 아무것도 못 보내고도 발송 완료로 처리되어 영영 재시도되지 않음).
    deliverable = []
    for channel in channels:
        sender = get_sender(channel)
        if sender is not None:
            deliverable.append((channel, sender))

    if not deliverable:
        logger.info(
            "사용자 %s: 발송 가능한 활성 채널 없음 → 건너뜀 (%d건 보류)",
            user_obj,
            len(inbox_notices),
        )
        return

    items = [alert_item_from_inbox(inbox) for inbox in inbox_notices]
    now = timezone.now()
    logs: list[AlertLog] = []
    any_sent = False

    for channel, sender in deliverable:
        summary["attempted"] += 1
        ok, error = _safe_send(sender, channel, items, user_obj)
        status = AlertLog.Status.SENT if ok else AlertLog.Status.FAILED
        logs.extend(
            AlertLog(
                inbox_notice_id=inbox,
                channel_id=channel,
                status=status,
                error="" if ok else (error or ""),
                sent_at=now if ok else None,
            )
            for inbox in inbox_notices
        )
        if ok:
            any_sent = True
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

    # 로그 기록과 notified_at 갱신을 하나의 트랜잭션으로 묶어, 둘 사이에서 크래시가 나
    # 'AlertLog=sent 인데 notified_at=NULL' 같은 어긋난 상태가 남지 않게 한다.
    # notified_at 은 '한 채널이라도 성공'했을 때만 갱신한다:
    #   - 전 채널 실패(일시적 SMTP/webhook 오류 등) → 미발송으로 남겨 다음 주기에 재시도(유실 방지).
    #   - 부분 성공 → 성공한 채널로의 중복 발송을 피하려 갱신한다(실패 채널은 재시도 안 함).
    with transaction.atomic():
        AlertLog.objects.bulk_create(logs)
        if any_sent:
            InboxNotice.objects.filter(
                id__in=[inbox.id for inbox in inbox_notices]
            ).update(notified_at=now)
    if any_sent:
        summary["users_notified"] += 1


def _safe_send(sender, channel, items, user_obj) -> tuple[bool, str]:
    """단일 채널 발송. 어떤 예외도 호출자에게 전파하지 않는다(NFR-3)."""

    try:
        return sender.send(items, user_obj)
    except Exception as exc:  # noqa: BLE001 - 방어적: 발송기 내부 계약을 넘어선 예외까지 격리
        logger.exception("발송기 예외 (채널=%s, 타입=%s)", channel.id, channel.type)
        return False, f"예상치 못한 오류: {type(exc).__name__}: {exc}"
