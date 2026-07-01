from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from typing import Iterable

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice
from .base import ScrapeContext, extract_body_text, first_text, make_notice, safe_href, take

# 잡코리아 AI잡스는 AJAX JSON으로 HTML 조각(`html` 필드)을 반환한다.
AJAX_URL = "https://www.jobkorea.co.kr/recruit/ai-jobs/GetRecruitList"
BODY_SELECTORS = ["#detail-content", ".view-content-detail"]


def _detail_iframe_url(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0] != "Recruit" or parts[1] != "GI_Read":
        return None
    gno = parts[2]
    sc = (parse_qs(parsed.query).get("sc") or [""])[0]
    return (
        "https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm"
        f"?sc={sc}&Gno={gno}&isHiringCenter=false&hideMapView=false"
    )


def parse_html_fragment(html: str, site: SiteConfig, defaults: Defaults) -> list[RawNotice]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out: list[RawNotice] = []
    for it in soup.select("li.recruit-item"):
        link = it.select_one("a.recruit-link")
        if not link:
            continue
        url = safe_href(link.get("href", ""), site.url)
        if not url:
            continue
        title = first_text(link.select_one(".recruit-title .title, h3.title"))
        company = first_text(it.select_one(".company-name a, .company-name"))
        notice = make_notice(
            site_id=site.id,
            title=f"[{company}] {title}" if company else title,
            url=url,
        )
        if notice:
            out.append(notice)
    return take(out, defaults.max_items_per_run)


def scrape(ctx: ScrapeContext) -> Iterable[RawNotice]:
    resp = ctx.client.get(
        AJAX_URL,
        headers={
            "Referer": ctx.site.url,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json,text/plain,*/*",
        },
        params={"pageNo": 1, "pageSize": 100},
    )
    resp.raise_for_status()
    data = resp.json()
    items = parse_html_fragment(data.get("html") or "", ctx.site, ctx.defaults)
    for item in items:
        iframe_url = _detail_iframe_url(str(item.url))
        if not iframe_url:
            continue
        detail = ctx.client.get(iframe_url, headers={"Referer": str(item.url)})
        detail.raise_for_status()
        item.body = extract_body_text(detail.text, BODY_SELECTORS)
    return items
