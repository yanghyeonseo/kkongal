from __future__ import annotations

import json
import re
from typing import Any, Iterable

from ..schemas import RawNotice
from .base import ScrapeContext, compact_text, make_notice, take

GOODS_URL = "https://tickets.interpark.com/goods/{goods_code}"


def scrape(ctx: ScrapeContext) -> Iterable[RawNotice]:
    resp = ctx.client.get(ctx.site.url)
    resp.raise_for_status()
    soup = ctx.soup(resp.text)
    data_node = soup.select_one("script#__NEXT_DATA__")
    if not data_node:
        return _scrape_links(ctx, resp.text)

    data = json.loads(data_node.get_text())
    page_props = data.get("props", {}).get("pageProps", {})
    rows = list(_walk_goods(page_props))

    notices: list[RawNotice] = []
    seen: set[str] = set()
    for row in rows:
        goods_code = _text(row.get("goodsCode") or row.get("goodsId") or row.get("goods_code"))
        title = _text(row.get("title") or row.get("goodsName"))
        url = _text(row.get("link")) or (GOODS_URL.format(goods_code=goods_code) if goods_code else "")
        if goods_code:
            url = GOODS_URL.format(goods_code=goods_code)
        if not title or not url or url in seen:
            continue
        seen.add(url)

        notice = make_notice(
            site_id=ctx.site.id,
            title=title,
            url=url,
            posted_at=_date(row.get("startDate")) or _date(row.get("playStartDate")),
            summary=_summary(row),
        )
        if not notice:
            continue
        notice.body = _body(row)
        notice.extra = {
            key: row.get(key)
            for key in (
                "goodsCode",
                "placeName",
                "playDate",
                "startDate",
                "endDate",
                "playStartDate",
                "playEndDate",
                "imageUrl",
            )
            if row.get(key) not in (None, "", [], {})
        }
        notices.append(notice)

    return take(notices, ctx.defaults.max_items_per_run)


def _scrape_links(ctx: ScrapeContext, html: str) -> list[RawNotice]:
    soup = ctx.soup(html)
    notices: list[RawNotice] = []
    seen: set[str] = set()
    for link in soup.select('a[href*="/goods/"]'):
        url = _text(link.get("href"))
        title = compact_text(link.get_text(" ", strip=True))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        notice = make_notice(site_id=ctx.site.id, title=title, url=url)
        if notice:
            notices.append(notice)
    return take(notices, ctx.defaults.max_items_per_run)


def _walk_goods(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if _is_goods(value):
            yield value
        for child in value.values():
            yield from _walk_goods(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_goods(child)


def _is_goods(row: dict[str, Any]) -> bool:
    has_code = any(row.get(key) for key in ("goodsCode", "goodsId", "goods_code"))
    has_title = any(row.get(key) for key in ("title", "goodsName"))
    link = _text(row.get("link"))
    if link and "tickets.interpark.com/goods/" not in link and "tickets.interpark.com/contents/bridge/" not in link:
        return False
    return bool(has_code and has_title)


def _summary(row: dict[str, Any]) -> str:
    parts = [
        _text(row.get("placeName")),
        _text(row.get("playDate")),
        _keywords(row.get("keywords")),
    ]
    return " / ".join(part for part in parts if part)


def _body(row: dict[str, Any]) -> str:
    lines = []
    for label, key in (
        ("장소", "placeName"),
        ("공연기간", "playDate"),
        ("티켓오픈", "startDate"),
        ("키워드", "keywords"),
        ("설명", "description"),
    ):
        if key == "keywords":
            value = _keywords(row.get(key))
        elif key == "startDate":
            value = _date(row.get(key)) or _text(row.get(key))
        else:
            value = _text(row.get(key))
        if value:
            lines.append(f"[{label}]\n{value}")
    return "\n\n".join(lines)


def _keywords(value: Any) -> str:
    if not isinstance(value, list):
        return _text(value)
    return ", ".join(
        _text(item.get("keyword") if isinstance(item, dict) else item)
        for item in value
        if _text(item.get("keyword") if isinstance(item, dict) else item)
    )


def _date(value: Any) -> str | None:
    text = re.sub(r"\D", "", _text(value))
    if len(text) >= 12:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]} {text[8:10]}:{text[10:12]}"
    if len(text) >= 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return None


def _text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return compact_text(str(value))
