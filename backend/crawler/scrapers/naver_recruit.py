from __future__ import annotations

from typing import Iterable

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice
from .base import ScrapeContext, hydrate_bodies, make_notice, take

# 네이버 채용은 SPA지만 AJAX JSON 엔드포인트가 공개되어 있어 playwright 없이 동작한다.
AJAX_URL = "https://recruit.navercorp.com/rcrt/loadJobList.do"
DETAIL_TEMPLATE = "https://recruit.navercorp.com/rcrt/view.do?annoId={anno_id}&lang=ko"
BODY_SELECTORS = [".detail_wrap"]


def parse_payload(payload: dict, site: SiteConfig, defaults: Defaults) -> list[RawNotice]:
    items = payload.get("list") or []
    out: list[RawNotice] = []
    for item in items:
        anno_id = item.get("annoId")
        title = (item.get("annoSubject") or "").strip()
        if not anno_id or not title:
            continue
        url = DETAIL_TEMPLATE.format(anno_id=anno_id)
        company = (item.get("sysCompanyCdNm") or "").strip()
        meta = " · ".join(
            x for x in (
                item.get("entTypeCdNm"),
                item.get("reqTypeCdNm"),
                item.get("stateCdNm"),
            ) if x
        )
        notice = make_notice(
            site_id=site.id,
            title=f"[{company}] {title}" if company else title,
            url=url,
            posted_at=item.get("staYmdTime") or None,
            summary=meta or None,
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
        params={"sortOrderBy": "newDt", "pageIndex": 1},
    )
    resp.raise_for_status()
    items = parse_payload(resp.json(), ctx.site, ctx.defaults)
    return hydrate_bodies(ctx, items, BODY_SELECTORS, headers={"Referer": ctx.site.url})
