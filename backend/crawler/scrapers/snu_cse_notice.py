from __future__ import annotations

import json
import re
from typing import Iterable

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice
from .base import ScrapeContext, extract_body_text, first_text, make_notice, safe_href, take

BODY_SELECTORS = [
    ".view-content",
    ".board-view",
    ".read-content",
    ".xe_content",
    ".fr-view",
    "article",
    ".content",
]
NOTICE_URL_RE = re.compile(r"/(?:ko/)?community/notice/\d+(?:[/?#]|$)")
BODY_JSON_PATTERNS = [
    re.compile(r'"html","(.*?)","cssRules"', re.DOTALL),
    re.compile(r'\\"html\\",\\"(.*?)\\",\\"cssRules\\"', re.DOTALL),
]


def _extract_streamed_body(html: str) -> str | None:
    for pattern in BODY_JSON_PATTERNS:
        m = pattern.search(html)
        if not m:
            continue
        try:
            html_fragment = json.loads(f'"{m.group(1)}"')
        except json.JSONDecodeError:
            continue
        body = extract_body_text(html_fragment, ["body", "html"])
        if body:
            return body
    return None


def parse_html(html: str, site: SiteConfig, defaults: Defaults) -> list[RawNotice]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("table tbody tr") or soup.select(
        "ul.board-list li, .notice-list li, li"
    )
    out: list[RawNotice] = []
    for row in rows:
        link = row.select_one("a[href]")
        if not link:
            continue
        url = safe_href(link.get("href", ""), site.url)
        if not url or not NOTICE_URL_RE.search(url):
            continue
        title = first_text(link)
        date_node = row.select_one(".date, .td-date, time, td:nth-of-type(4), td:nth-of-type(5)")
        notice = make_notice(
            site_id=site.id,
            title=title,
            url=url,
            posted_at=first_text(date_node) or None,
        )
        if notice:
            out.append(notice)
    return take(out, defaults.max_items_per_run)


def scrape(ctx: ScrapeContext) -> Iterable[RawNotice]:
    resp = ctx.client.get(ctx.site.url)
    resp.raise_for_status()
    items = parse_html(resp.text, ctx.site, ctx.defaults)
    for item in items:
        detail = ctx.client.get(str(item.url))
        detail.raise_for_status()
        item.body = _extract_streamed_body(detail.text) or extract_body_text(detail.text, BODY_SELECTORS)
    return items
