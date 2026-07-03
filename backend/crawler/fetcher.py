from __future__ import annotations

import httpx
from django.conf import settings

from .config_loader import Defaults


def http_client(defaults: Defaults) -> httpx.Client:
    headers = {
        "User-Agent": defaults.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    return httpx.Client(
        headers=headers,
        timeout=defaults.request_timeout_seconds,
        follow_redirects=True,
        # 기본은 TLS 인증서 검증 활성화(MITM 으로 주입된 HTML 이 저장·LLM·알림까지 흐르는 것을 방지).
        # 인증서 체인이 깨진 특정 사이트 때문에만 CRAWLER_VERIFY_TLS=False 로 완화할 수 있다.
        verify=getattr(settings, "CRAWLER_VERIFY_TLS", True),
        trust_env=False,
    )
