from __future__ import annotations

from typing import Iterable

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice
from .base import ScrapeContext, extract_body_text, find_row_date, first_text, make_notice, safe_href, take

BODY_SELECTORS = [
    ".bbs_contents",
    ".board-view",
    ".view-cont",
    ".news-view",
    ".xe_content",
    ".fr-view",
    "article",
    ".content",
]


def parse_html(html: str, site: SiteConfig, defaults: Defaults) -> list[RawNotice]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    rows = (
        soup.select(".board-list tr, .news-list li, .notice-list li, table tbody tr")
        or soup.select("li:has(a)")
    )
    out: list[RawNotice] = []
    for row in rows:
        link = row.select_one("a[href]")
        if not link:
            continue
        url = safe_href(link.get("href", ""), site.url)
        if not url:
            continue
        title = first_text(row.select_one(".title, .subject, strong")) or first_text(link)
        # 게시일은 4번째 <td>(예: "2026-07-02")에 ISO 로 들어있다.
        posted_at = find_row_date(row, selectors=(".date", "time", ".reg-date"))
        notice = make_notice(
            site_id=site.id,
            title=title,
            url=url,
            posted_at=posted_at,
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
        item.body = extract_body_text(detail.text, BODY_SELECTORS)
    return items
