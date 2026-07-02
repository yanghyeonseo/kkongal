from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Optional

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice
from .base import ScrapeContext, make_notice, take

# 네이버 카페 공식 SPA가 사용하는 공개 게시글 목록 AJAX.
# clubid(=cafeId)와 menuid는 sites.json에 등록된 cafe URL에서 추출한다.
AJAX_URL = "https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json"
URL_PATTERN = re.compile(r"cafes/(?P<cafe>\d+)/menus/(?P<menu>\d+)")
ARTICLE_TEMPLATE = "https://cafe.naver.com/f-e/cafes/{cafe_id}/articles/{article_id}"


def _ids_from_url(url: str) -> Optional[tuple[str, str]]:
    m = URL_PATTERN.search(url)
    if not m:
        return None
    return m.group("cafe"), m.group("menu")


def _ts_to_iso(ts_ms) -> Optional[str]:
    if not isinstance(ts_ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def parse_payload(payload: dict, site: SiteConfig, defaults: Defaults) -> list[RawNotice]:
    ids = _ids_from_url(site.url)
    if not ids:
        return []
    cafe_id, _ = ids
    articles = (
        ((payload.get("message") or {}).get("result") or {}).get("articleList") or []
    )
    out: list[RawNotice] = []
    for art in articles:
        article_id = art.get("articleId")
        title = (art.get("subject") or "").strip()
        if not article_id or not title:
            continue
        url = ARTICLE_TEMPLATE.format(cafe_id=cafe_id, article_id=article_id)
        nickname = (art.get("writerNickname") or "").strip()
        bits = []
        if nickname:
            bits.append(f"by {nickname}")
        if (rc := art.get("readCount")):
            bits.append(f"조회 {rc}")
        if (cc := art.get("commentCount")):
            bits.append(f"댓글 {cc}")
        notice = make_notice(
            site_id=site.id,
            title=title,
            url=url,
            posted_at=_ts_to_iso(art.get("writeDateTimestamp")),
            summary=" · ".join(bits) or None,
        )
        if notice:
            out.append(notice)
    return take(out, defaults.max_items_per_run)


def scrape(ctx: ScrapeContext) -> Iterable[RawNotice]:
    ids = _ids_from_url(ctx.site.url)
    if not ids:
        raise ValueError(
            f"cafeId/menuId를 URL에서 추출하지 못함: {ctx.site.url} "
            "(예상 형식: https://cafe.naver.com/f-e/cafes/<cafeId>/menus/<menuId>)"
        )
    cafe_id, menu_id = ids
    resp = ctx.client.get(
        AJAX_URL,
        headers={
            "Referer": ctx.site.url,
            "Accept": "application/json,text/plain,*/*",
        },
        params={
            "search.clubid": cafe_id,
            "search.menuid": menu_id,
            "search.boardtype": "L",
            "search.questionTab": "A",
            "search.queryType": "lastArticle",
            "search.page": 1,
            "search.perPage": ctx.defaults.max_items_per_run,
        },
    )
    resp.raise_for_status()
    return parse_payload(resp.json(), ctx.site, ctx.defaults)
