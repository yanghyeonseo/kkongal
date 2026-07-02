from __future__ import annotations

from typing import Iterable

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice
from .base import ScrapeContext, extract_body_text, first_text, make_notice, safe_href, take

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
        notice = make_notice(
            site_id=site.id,
            title=title,
            url=url,
            posted_at=first_text(row.select_one(".date, time, .reg-date")) or None,
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
