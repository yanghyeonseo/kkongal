"""사이트 표시명·파비콘 계산 헬퍼 — 네트워크 왕복 없이 URL 만으로 결정한다.

- 파비콘: Google s2 파비콘 서비스(``https://www.google.com/s2/favicons?domain=...``).
  각 사이트를 직접 받아오지 않아도 항상 해석되므로 등록이 느려지거나 실패하지 않는다.
- 표시명: 카탈로그(``crawler/config/sites.json``)에 있는 url 이면 그 사이트의 사람이
  읽는 이름을 쓰고, 없으면 도메인에서 읽기 쉬운 이름을 만든다.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from crawler.config_loader import CrawlerConfig, load_config

# Google s2 파비콘 서비스. sz=64 로 고해상도 아이콘을 받는다.
_FAVICON_ENDPOINT = "https://www.google.com/s2/favicons?domain={host}&sz=64"


def _host_of(url: str) -> str:
    """url 의 호스트(소문자, 포트 제외). 파싱 실패 시 빈 문자열."""
    try:
        return (urlparse(url).hostname or "").strip()
    except (ValueError, TypeError):
        return ""


def favicon_url_for(url: str) -> str:
    """url 호스트에 대한 Google s2 파비콘 URL. 호스트를 못 구하면 빈 문자열."""
    host = _host_of(url)
    if not host:
        return ""
    return _FAVICON_ENDPOINT.format(host=host)


def friendly_name_for(url: str, config: Optional[CrawlerConfig] = None) -> str:
    """사람이 읽는 표시명.

    카탈로그에 등록된 url 이면 그 사이트 이름(예: '사람인 HOT100')을, 아니면 도메인에서
    ``www.`` 를 뗀 호스트(예: 'recruit.navercorp.com')를 돌려준다. 호스트도 못 구하면
    원본 url 을 그대로 쓴다(빈 이름 방지).
    """
    config = config or load_config()
    site = next((s for s in config.sites if s.url == url), None)
    if site is not None:
        return site.name

    host = _host_of(url)
    if host.startswith("www."):
        host = host[4:]
    return host or url
