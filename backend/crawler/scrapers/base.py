from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice

log = logging.getLogger("crawler.parse")

# 목록 셀 하나의 텍스트가 "순수 날짜"인지 판별한다(제목에 섞인 날짜와 구분).
# 예: 2026/7/01, 2026-07-02, 2026.07.02, 2026-07-02 14:30
_PURE_DATE_RE = re.compile(
    r"^\s*20\d{2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2}\.?"
    r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$"
)


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


def find_row_date(row: Tag, selectors: Iterable[str] = ()) -> Optional[str]:
    """목록 행(row)에서 게시일 문자열을 뽑는다.

    사이트 목록의 날짜 셀은 클래스가 불안정(Tailwind 등)하거나 아예 클래스가 없어
    고정 셀렉터만으로는 잡히지 않는 경우가 많다. 그래서:
      1) 힌트 셀렉터(``.date`` 등)가 주어지면 먼저 시도하고,
      2) 실패하면 행 안에서 **텍스트 전체가 순수 날짜인** 요소를 찾아 그 값을 쓴다.

    2)는 제목에 섞인 날짜(예: "2026년 하반기", "(~7/15)")를 오탐하지 않는다 —
    연도 포함 ``YYYY[./-]M[./-]D`` 형태의 셀만 매칭하기 때문.
    """
    for selector in selectors:
        node = row.select_one(selector)
        text = first_text(node)
        if text:
            return text

    for element in row.find_all(["td", "span", "time", "p", "dd", "div"]):
        text = element.get_text(" ", strip=True)
        if _PURE_DATE_RE.match(text):
            return " ".join(text.split())
    return None


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
