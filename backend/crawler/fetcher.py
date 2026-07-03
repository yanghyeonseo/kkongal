from __future__ import annotations

import httpx

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
        verify=False,
        trust_env=False,
    )
