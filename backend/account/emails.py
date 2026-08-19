"""이메일 소유 확인 메일 발송.

가입 직후(그리고 재발송 요청 시) 인증 링크를 보낸다. 발송은 항상 백그라운드
스레드에서 돌린다 — SMTP 왕복이 느리거나 멈춰도 가입 응답이 그만큼 지연되면
안 되기 때문이다(alert/senders.py 의 send_channel_connected_async 와 같은 이유).

발송기는 예외를 호출자에게 던지지 않는다. 메일이 안 나가도 가입 자체는 성공해야
하고, 사용자는 화면의 "인증 메일 다시 보내기"로 재시도할 수 있다.
"""

from __future__ import annotations

import html
import logging
import threading
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .models import EmailVerification

logger = logging.getLogger("account")

BRAND = "꽁알꽁알"


def build_verification_url(raw_token: str) -> str:
    """메일에 실을 인증 링크. SPA 가 이 경로에서 토큰을 읽어 API 로 넘긴다."""
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/verify-email?token={quote(raw_token)}"


def _text_body(display_name: str, url: str, ttl_hours: int) -> str:
    return (
        f"{display_name}님, 반가워요!\n\n"
        f"{BRAND} 가입을 마치려면 아래 링크에서 이메일을 인증해주세요.\n"
        f"인증을 마쳐야 관심 공지 알림을 메일로 받아볼 수 있어요.\n\n"
        f"{url}\n\n"
        f"이 링크는 {ttl_hours}시간 동안만 유효해요.\n"
        f"본인이 요청한 게 아니라면 이 메일은 무시하셔도 됩니다.\n"
    )


def _html_body(display_name: str, url: str, ttl_hours: int) -> str:
    safe_name = html.escape(display_name)
    safe_url = html.escape(url)
    return f"""\
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f6f8;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;font-family:'Apple SD Gothic Neo',-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;color:#202124;">
    <div style="text-align:center;margin-bottom:20px;">
      <span style="font-size:20px;font-weight:700;color:#1a73e8;">🐣 {BRAND}</span>
    </div>
    <div style="background:#ffffff;border-radius:12px;padding:28px 24px;">
      <h2 style="margin:0 0 12px;font-size:18px;">{safe_name}님, 반가워요!</h2>
      <p style="margin:0 0 20px;font-size:14px;color:#3c4043;line-height:1.6;">
        가입을 마치려면 아래 버튼을 눌러 이메일을 인증해주세요.<br>
        인증을 마쳐야 관심 공지 알림을 메일로 받아볼 수 있어요.
      </p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{safe_url}" style="display:inline-block;padding:12px 28px;background:#1a73e8;color:#ffffff;border-radius:8px;text-decoration:none;font-size:15px;font-weight:600;">이메일 인증하기</a>
      </div>
      <p style="margin:20px 0 0;font-size:12px;color:#5f6368;line-height:1.6;">
        버튼이 눌리지 않으면 아래 주소를 브라우저에 붙여넣어 주세요.<br>
        <span style="word-break:break-all;color:#1a73e8;">{safe_url}</span>
      </p>
      <p style="margin:16px 0 0;font-size:12px;color:#5f6368;">
        이 링크는 {ttl_hours}시간 동안만 유효해요.
      </p>
    </div>
    <p style="text-align:center;margin:16px 0 0;font-size:11px;color:#9aa0a6;">
      본인이 요청한 게 아니라면 이 메일은 무시하셔도 됩니다.
    </p>
  </div>
</body>
</html>"""


def send_verification_email(user, raw_token: str) -> tuple[bool, str]:
    """인증 메일을 동기 발송한다. ``(ok, error)`` 를 돌려주고 예외는 던지지 않는다."""

    ttl_hours = settings.EMAIL_VERIFICATION_TTL_HOURS
    url = build_verification_url(raw_token)
    recipient = (user.email or "").strip()
    if not recipient:
        return False, "수신 이메일이 비어 있습니다."

    try:
        message = EmailMultiAlternatives(
            subject=f"[{BRAND}] 이메일 인증을 완료해주세요",
            body=_text_body(user.display_name, url, ttl_hours),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        message.attach_alternative(_html_body(user.display_name, url, ttl_hours), "text/html")
        message.send(fail_silently=False)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - 발송 실패가 가입을 막으면 안 된다
        logger.warning("인증 메일 발송 실패 (user_id=%s): %s", user.id, exc)
        return False, str(exc)


def issue_and_send_verification(user) -> threading.Thread:
    """토큰을 발급하고 인증 메일을 백그라운드로 보낸다.

    토큰 발급(DB 쓰기)은 호출한 요청 스레드에서 끝내고, 느릴 수 있는 SMTP 왕복만
    별도 스레드로 넘긴다. 이렇게 해야 스레드가 ORM 을 건드리지 않아 DB 커넥션
    정리를 신경 쓸 필요가 없다(alert/senders.py 와 같은 패턴).

    반환된 스레드는 테스트에서 ``join`` 해 결정적으로 검증할 수 있다.
    """

    _record, raw_token = EmailVerification.issue(
        user, ttl_hours=settings.EMAIL_VERIFICATION_TTL_HOURS
    )

    def _run():
        try:
            send_verification_email(user, raw_token)
        except Exception:  # noqa: BLE001 - 백그라운드 스레드가 조용히 죽지 않도록
            logger.exception("인증 메일 발송 스레드 오류 (user_id=%s)", user.id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
