"""알림 채널별 발송기 (senders).

각 발송기는 공통 인터페이스를 가진다:

    sender = get_sender(channel)          # 채널 타입에 맞는 발송기 (없으면 None)
    ok, error = sender.send(items, user)  # 실제 공지 알림 발송
    ok, error = sender.send_test(user)    # "테스트 발송" (채널 연결 확인용)

반환 계약: 항상 ``(ok: bool, error: str)``. 발송기는 절대 호출자에게 예외를
던지지 않는다 — 모든 오류는 잡아서 ``error`` 문자열로 돌려준다. 이로써
디스패처의 한 채널 실패가 다른 채널/유저 발송을 막지 않는다(NFR-3).

새 채널을 추가하려면 :class:`BaseSender` 를 상속해 ``channel_type`` 과
``send``/``send_test`` 를 구현하고 :data:`SENDER_REGISTRY` 에 등록하면 된다(NFR-4).
"""

from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass

import httpx
from django.conf import settings

logger = logging.getLogger("alert")

# 한 메시지에 담는 공지 최대 개수(가독성/페이로드 크기 제한). 초과분은 요약 표시.
MAX_ITEMS_PER_MESSAGE = 10

BRAND = "꽁알꽁알"


@dataclass
class AlertItem:
    """발송기가 렌더링에 사용하는, ORM 과 분리된 공지 표현."""

    title: str
    source: str = ""
    reason: str = ""
    keywords: str = ""
    url: str = ""
    score: float | None = None


def alert_item_from_inbox(inbox_notice) -> AlertItem:
    """``InboxNotice`` 를 렌더링용 :class:`AlertItem` 으로 변환한다."""

    notice = inbox_notice.notice_id
    source = getattr(notice, "source_id", None)
    source_name = ""
    if source is not None:
        source_name = source.name or source.url or ""
    return AlertItem(
        title=(notice.title or "(제목 없음)").strip(),
        source=source_name,
        reason=(inbox_notice.reason or "").strip(),
        keywords=inbox_notice.matched_keywords or "",
        url=notice.url or "",
        score=inbox_notice.relevance_score,
    )


def _test_item() -> AlertItem:
    """채널 연결 확인용 친근한 테스트 항목."""

    return AlertItem(
        title="테스트 알림이 정상적으로 도착했어요 🎉",
        source=BRAND,
        reason="이 메시지가 보이면 알림 채널이 올바르게 연결된 것입니다. 이제 관심 공지가 뜨면 여기로 알려드릴게요!",
        keywords="",
        url=settings.FRONTEND_URL,
        score=None,
    )


def _format_keywords(raw) -> list[str]:
    """저장된 matched_keywords(콤마 조인 문자열/JSON 배열/리스트)를 키워드 목록으로."""

    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(k).strip() for k in raw if str(k).strip()]
    text = str(raw).strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(k).strip() for k in parsed if str(k).strip()]
        except (ValueError, TypeError):
            pass
    return [k.strip() for k in text.split(",") if k.strip()]


def _subject_for(items: list[AlertItem]) -> str:
    if len(items) == 1:
        title = items[0].title
        if len(title) > 60:
            title = title[:57] + "..."
        return f"[{BRAND}] {title}"
    return f"[{BRAND}] 관심 공지 {len(items)}건이 도착했어요"


class BaseSender:
    """모든 발송기의 공통 베이스. 하위 클래스는 ``channel_type`` 을 지정한다."""

    channel_type: str = ""

    def __init__(self, channel):
        self.channel = channel

    @property
    def config(self) -> dict:
        return self.channel.config or {}

    def send(self, items: list[AlertItem], user) -> tuple[bool, str]:
        raise NotImplementedError

    def send_test(self, user) -> tuple[bool, str]:
        raise NotImplementedError


class EmailSender(BaseSender):
    """Django 메일 프레임워크(``EmailMultiAlternatives``)로 HTML+평문 메일 발송.

    수신자 = ``config["address"]`` → 없으면 ``user.email``. 기본 EMAIL_BACKEND 는
    콘솔이라 SMTP 자격 증명 없이도 동작한다.
    """

    channel_type = "email"

    def _recipient(self, user) -> str:
        address = (self.config.get("address") or "").strip()
        if address:
            return address
        return (getattr(user, "email", "") or "").strip()

    def send(self, items, user):
        return self._deliver(
            user,
            subject=_subject_for(items),
            items=items,
            intro="",
        )

    def send_test(self, user):
        # 테스트 발송은 반드시 본인(회원) 이메일로만 보낸다. 사용자가 지정한
        # config.address 로는 보내지 않아, 임의 수신자에게 메일을 쏘는 증폭기로
        # 악용되는 것을 막는다(M4). 실제 dispatch 는 여전히 config.address 를 따른다.
        recipient = (getattr(user, "email", "") or "").strip()
        if not recipient:
            return False, "회원 이메일이 없어 테스트를 보낼 수 없습니다"
        return self._deliver(
            user,
            subject=f"[{BRAND}] 알림 채널 테스트 ✅",
            items=[_test_item()],
            intro="채널이 정상적으로 연결되었는지 확인하기 위한 테스트 메시지입니다.",
            recipient=recipient,
        )

    def _deliver(self, user, subject, items, intro, recipient=None):
        # 지연 import: 발송 시점에만 메일 프레임워크를 끌어온다.
        from django.core.mail import EmailMultiAlternatives

        if recipient is None:
            recipient = self._recipient(user)
        if not recipient:
            return False, "수신 이메일이 없습니다 (channel.config.address 와 user.email 모두 비어 있음)"

        text_body = self._render_text(items, intro)
        html_body = self._render_html(items, intro)
        try:
            message = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
            )
            message.attach_alternative(html_body, "text/html")
            sent = message.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - 계약상 오류를 문자열로 반환
            return False, f"{type(exc).__name__}: {exc}"

        if not sent:
            return False, "메일 백엔드가 0건 발송을 보고했습니다"
        return True, ""

    def _render_text(self, items, intro) -> str:
        lines: list[str] = [BRAND]
        if intro:
            lines.append("")
            lines.append(intro)
        for idx, item in enumerate(items, start=1):
            lines.append("")
            lines.append(f"[{idx}] {item.title}")
            if item.source:
                lines.append(f"    출처: {item.source}")
            if item.reason:
                lines.append(f"    선별 이유: {item.reason}")
            keywords = _format_keywords(item.keywords)
            if keywords:
                lines.append(f"    키워드: {', '.join(keywords)}")
            if item.url:
                lines.append(f"    원문 보기: {item.url}")
        lines.append("")
        lines.append(f"대시보드에서 모아보기: {settings.FRONTEND_URL}")
        return "\n".join(lines)

    def _render_html(self, items, intro) -> str:
        cards: list[str] = []
        for item in items:
            title = html.escape(item.title)
            title_html = (
                f'<a href="{html.escape(item.url)}" '
                f'style="color:#1a73e8;text-decoration:none;">{title}</a>'
                if item.url
                else title
            )
            rows = [
                f'<h3 style="margin:0 0 8px;font-size:16px;line-height:1.4;">{title_html}</h3>'
            ]
            if item.source:
                rows.append(
                    '<p style="margin:0 0 4px;font-size:13px;color:#5f6368;">'
                    f"출처 · {html.escape(item.source)}</p>"
                )
            if item.reason:
                rows.append(
                    '<p style="margin:8px 0 0;font-size:14px;color:#3c4043;line-height:1.5;">'
                    f"{html.escape(item.reason)}</p>"
                )
            keywords = _format_keywords(item.keywords)
            if keywords:
                chips = "".join(
                    '<span style="display:inline-block;margin:0 6px 6px 0;padding:2px 10px;'
                    "background:#e8f0fe;color:#1a73e8;border-radius:12px;font-size:12px;\">"
                    f"{html.escape(kw)}</span>"
                    for kw in keywords
                )
                rows.append(f'<div style="margin-top:10px;">{chips}</div>')
            if item.url:
                rows.append(
                    '<div style="margin-top:12px;">'
                    f'<a href="{html.escape(item.url)}" '
                    'style="display:inline-block;padding:8px 16px;background:#1a73e8;color:#ffffff;'
                    'border-radius:6px;text-decoration:none;font-size:13px;">원문 보기 →</a></div>'
                )
            cards.append(
                '<div style="border:1px solid #e0e0e0;border-radius:10px;padding:18px 20px;'
                'margin:0 0 16px;background:#ffffff;">' + "".join(rows) + "</div>"
            )

        intro_html = (
            f'<p style="margin:0 0 20px;font-size:14px;color:#3c4043;line-height:1.6;">'
            f"{html.escape(intro)}</p>"
            if intro
            else ""
        )
        heading = (
            "관심 공지가 도착했어요"
            if not intro
            else "알림 채널 테스트"
        )
        return f"""\
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f6f8;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;font-family:'Apple SD Gothic Neo',-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;color:#202124;">
    <div style="text-align:center;margin-bottom:20px;">
      <span style="font-size:20px;font-weight:700;color:#1a73e8;">🐣 {BRAND}</span>
    </div>
    <div style="background:#ffffff;border-radius:12px;padding:24px;">
      <h2 style="margin:0 0 16px;font-size:18px;">{heading}</h2>
      {intro_html}
      {''.join(cards)}
      <div style="text-align:center;margin-top:8px;">
        <a href="{html.escape(settings.FRONTEND_URL)}" style="display:inline-block;padding:10px 22px;background:#202124;color:#ffffff;border-radius:8px;text-decoration:none;font-size:14px;">대시보드에서 모아보기</a>
      </div>
    </div>
    <p style="text-align:center;margin:16px 0 0;font-size:11px;color:#9aa0a6;">
      본 메일은 {BRAND} 알림 설정에 따라 발송되었습니다.
    </p>
  </div>
</body>
</html>"""


def _slack_escape(text: str) -> str:
    """Slack mrkdwn 이스케이프 (링크/서식 텍스트에 사용)."""

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class SlackSender(BaseSender):
    """Incoming Webhook 으로 Block Kit 페이로드 POST (httpx).

    webhook_url = ``config["webhook_url"]`` → 없으면 전역 폴백
    ``settings.SLACK_DEFAULT_WEBHOOK_URL``. 2xx 가 아니거나 응답 본문이
    ``ok`` 가 아니면(비어 있지 않은 경우) 실패로 간주한다.
    """

    channel_type = "slack"

    def _webhook_url(self) -> str:
        url = (self.config.get("webhook_url") or "").strip()
        if url:
            return url
        return (getattr(settings, "SLACK_DEFAULT_WEBHOOK_URL", "") or "").strip()

    def send(self, items, user):
        return self._deliver(
            header=f"🐣 {BRAND} · 관심 공지 {len(items)}건",
            fallback=self._fallback_text(items),
            items=items,
            intro="",
        )

    def send_test(self, user):
        item = _test_item()
        return self._deliver(
            header=f"🐣 {BRAND} · 알림 채널 테스트 ✅",
            fallback="꽁알꽁알 알림 채널 테스트 메시지입니다.",
            items=[item],
            intro="채널이 정상적으로 연결되었는지 확인하기 위한 테스트 메시지입니다.",
        )

    def _fallback_text(self, items) -> str:
        if len(items) == 1:
            return f"[{BRAND}] {items[0].title}"
        return f"[{BRAND}] 관심 공지 {len(items)}건이 도착했어요"

    def _deliver(self, header, fallback, items, intro):
        webhook_url = self._webhook_url()
        if not webhook_url:
            return False, "슬랙 webhook_url 이 설정되지 않았습니다 (channel.config.webhook_url)"

        payload = self._build_payload(header, fallback, items, intro)
        try:
            response = httpx.post(
                webhook_url,
                json=payload,
                timeout=settings.SLACK_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - 계약상 오류를 문자열로 반환
            return False, f"{type(exc).__name__}: {exc}"

        # 업스트림(슬랙) 응답 본문은 로그에만 남기고, API 로 노출하는 error 는
        # 일반화된 메시지만 반환한다(응답 본문 반사/정보 노출 방지).
        if response.status_code // 100 != 2:
            logger.warning(
                "슬랙 전송 실패 HTTP %s: %s",
                response.status_code,
                (response.text or "")[:500],
            )
            return False, f"슬랙 전송 실패 (HTTP {response.status_code})"

        body = (response.text or "").strip()
        if body and body != "ok":
            logger.warning("슬랙 응답 본문이 ok 가 아님: %s", body[:500])
            return False, "슬랙 전송 실패 (예상치 못한 응답)"
        return True, ""

    def _build_payload(self, header, fallback, items, intro) -> dict:
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": header, "emoji": True},
            }
        ]
        if intro:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": _slack_escape(intro)},
                }
            )
            blocks.append({"type": "divider"})

        for item in items[:MAX_ITEMS_PER_MESSAGE]:
            title = _slack_escape(item.title)
            if item.url:
                heading = f"*<{item.url}|{title}>*"
            else:
                heading = f"*{title}*"
            lines = [heading]
            if item.source:
                lines.append(f"🏷 출처 · {_slack_escape(item.source)}")
            if item.reason:
                lines.append(f"💡 {_slack_escape(item.reason)}")
            keywords = _format_keywords(item.keywords)
            if keywords:
                lines.append(
                    "🔎 " + " ".join(f"`{_slack_escape(kw)}`" for kw in keywords)
                )
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}
            )
            blocks.append({"type": "divider"})

        remaining = len(items) - MAX_ITEMS_PER_MESSAGE
        if remaining > 0:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"외 {remaining}건 더 있어요."}
                    ],
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{settings.FRONTEND_URL}|꽁알꽁알 대시보드에서 모아보기 →>",
                    }
                ],
            }
        )
        return {"text": fallback, "blocks": blocks}


# 채널 타입 → 발송기 클래스. 새 채널은 여기에 등록만 하면 된다(NFR-4).
SENDER_REGISTRY: dict[str, type[BaseSender]] = {
    EmailSender.channel_type: EmailSender,
    SlackSender.channel_type: SlackSender,
}


def get_sender(channel) -> BaseSender | None:
    """채널 타입에 맞는 발송기 인스턴스. 지원하지 않는 타입이면 ``None``."""

    sender_cls = SENDER_REGISTRY.get(channel.type)
    if sender_cls is None:
        return None
    return sender_cls(channel)
