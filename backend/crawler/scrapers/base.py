from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice

log = logging.getLogger("crawler.parse")


@dataclass
class ScrapeContext:
    """스크래퍼가 fetch + parse를 모두 수행할 수 있도록 httpx 클라이언트를 들고 다닌다."""

    site: SiteConfig
    defaults: Defaults
    client: httpx.Client

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def absolute(self, href: str) -> str:
        return urljoin(self.site.url, href)


Scraper = Callable[[ScrapeContext], Iterable[RawNotice]]


def first_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def compact_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split())


def safe_href(href: str | None, base_url: str) -> Optional[str]:
    """비 http(s) 링크(javascript:, mailto:, 빈 anchor)를 거른다."""
    if not href:
        return None
    h = href.strip()
    if not h or h.startswith("#"):
        return None
    full = urljoin(base_url, h)
    if not full.startswith(("http://", "https://")):
        return None
    return full


def extract_body_text(html: str, selectors: list[str]) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    for selector in selectors:
        node = soup.select_one(selector)
        text = compact_text(node.get_text("\n", strip=True) if node else "")
        if text:
            return text
    return None


def extract_meta_content(html: str, names: list[str]) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    wanted = {name.lower() for name in names}
    for meta in soup.select("meta[content]"):
        key = (meta.get("name") or meta.get("property") or "").strip().lower()
        if key in wanted:
            content = compact_text(meta.get("content"))
            if content:
                return content
    return None


def make_notice(
    *,
    site_id: str,
    title: str,
    url: str | None,
    posted_at: Optional[str] = None,
    summary: Optional[str] = None,
) -> Optional[RawNotice]:
    """RawNotice 생성 실패는 한 건만 버리고 통과시킨다 — 한 항목 검증 실패가
    제너레이터 전체를 죽이지 않게 하기 위한 안전장치."""
    if not url or not title:
        return None
    cleaned_title = title.strip()
    if len(cleaned_title) < 2:
        return None
    try:
        return RawNotice(
            source_id=site_id,
            title=cleaned_title,
            url=url,
            posted_at=posted_at,
            summary=summary,
        )
    except Exception as exc:  # pydantic ValidationError 포함
        log.debug("skip invalid notice (%s): %r", exc, {"title": cleaned_title, "url": url})
        return None


def take(items: Iterable[RawNotice], limit: int) -> list[RawNotice]:
    out: list[RawNotice] = []
    for item in items:
        out.append(item)
        if len(out) >= limit:
            break
    return out
