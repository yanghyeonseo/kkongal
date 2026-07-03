"""LLM 학습형 셀렉터 전략 — 최후 수단(rss/json_api/heuristic 모두 실패했을 때만).

목록 페이지 HTML 스니펫을 LLM 에게 보여주고 CSS 셀렉터 레시피(row/title/link/date)를
딱 한 번 받아낸 뒤, 그 레시피를 결정론적으로 적용한다. 레시피는 profile 로 저장되어
다음 크롤부터는 LLM 호출 없이 fast-path 로 재사용된다(``spec.extraction_profile["row"]``).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

from ...scrapers.base import find_row_date, first_text, make_notice, safe_href
from ...schemas import RawNotice
from ..base import Fetcher, SourceSpec, StrategyOutcome

log = logging.getLogger("crawler.generic.llm_selector")

_MAX_ITEMS = 50
# LLM 에 보낼 HTML 스니펫 상한(토큰/비용 방어). script/style 제거 후 자른다.
_MAX_HTML_CHARS = 12000

_SYSTEM_MESSAGE = (
    "너는 웹 페이지 HTML 을 보고 공지/게시판 목록의 CSS 셀렉터를 뽑아내는 도구다. "
    "설명이나 코드펜스 없이 순수 JSON 객체 하나만 응답하라."
)


def extract(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome:
    """LLM 셀렉터 전략 진입점. 이 함수는 절대 예외를 밖으로 던지지 않는다."""
    try:
        return _extract(spec, fetch)
    except Exception as exc:  # noqa: BLE001 - 전략 하나의 실패가 오케스트레이터를 죽이면 안 된다.
        log.debug("llm_selector extract failed for %s: %r", spec.url, exc)
        return StrategyOutcome(kind="llm_profile", items=[], note=f"error: {exc!r}")


def _extract(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome:
    profile = spec.extraction_profile or {}

    # 1) fast-path: 이전 크롤에서 학습된 레시피가 있으면 LLM 호출 없이 바로 적용한다.
    if profile.get("row"):
        recipe = _sanitize_recipe(profile)
        if recipe is None:
            return StrategyOutcome(
                kind="llm_profile", items=[], note="fast-path: stored recipe incomplete"
            )
        result = fetch(spec.url)
        if not result.ok or not result.text:
            return StrategyOutcome(kind="llm_profile", items=[], note="fast-path: fetch failed")
        items = _apply_recipe(spec, result.text, result.url, recipe)
        if items:
            return StrategyOutcome(
                kind="llm_profile",
                items=items,
                profile=recipe,
                note="fast-path: learned recipe",
            )
        return StrategyOutcome(
            kind="llm_profile", items=[], note="fast-path: recipe produced no items"
        )

    # 2) LLM 에게 레시피를 딱 한 번 물어본다.
    from ai.llm import get_client  # 지연 import: crawler 앱이 ai 앱에 하드 의존하지 않게.

    client = get_client()
    if not client.enabled:
        return StrategyOutcome(kind="llm_profile", items=[], note="llm disabled")

    result = fetch(spec.url)
    if not result.ok or not result.text:
        return StrategyOutcome(kind="llm_profile", items=[], note="fetch failed")

    snippet = _trim_html(result.text)
    if not snippet:
        return StrategyOutcome(kind="llm_profile", items=[], note="empty html snippet")

    messages = [
        {"role": "system", "content": _SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": (
                "다음은 게시판/공지 목록 페이지의 HTML 일부다. 목록의 각 항목(row)을 고르는 "
                "CSS 셀렉터와, 그 row 안에서 상대적으로 제목/링크/날짜를 뽑아낼 CSS 셀렉터를 "
                "알려줘. 링크 셀렉터는 반드시 <a> 태그를 가리켜야 한다. 날짜 셀렉터를 모르겠으면 "
                "빈 문자열로 둬라. 아래 형태의 JSON 객체 하나만 응답해라:\n"
                '{"row": "css selector", "title": "css selector", "link": "css selector", '
                '"date": "css selector or empty"}\n\n'
                f"HTML:\n{snippet}"
            ),
        },
    ]

    data = client.complete_json(messages)
    recipe = _sanitize_recipe(data)
    if recipe is None:
        return StrategyOutcome(kind="llm_profile", items=[], note="llm recipe unusable")

    items = _apply_recipe(spec, result.text, result.url, recipe)
    if not items:
        return StrategyOutcome(kind="llm_profile", items=[], note="llm recipe produced no items")

    return StrategyOutcome(
        kind="llm_profile", items=items, profile=recipe, note="llm-generated recipe"
    )


# -- helpers ------------------------------------------------------------------


def _trim_html(html: str) -> str:
    """<script>/<style> 를 제거하고 토큰을 아끼기 위해 길이 상한을 둔다."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001
        log.debug("html parse failed: %r", exc)
        return ""
    for tag in soup(["script", "style"]):
        tag.decompose()
    return str(soup)[:_MAX_HTML_CHARS]


def _sanitize_recipe(data: Any) -> Optional[dict]:
    """레시피 후보에서 row/title/link 가 모두 비어있지 않은 문자열일 때만 인정한다."""
    if not isinstance(data, dict):
        return None
    row = str(data.get("row") or "").strip()
    title = str(data.get("title") or "").strip()
    link = str(data.get("link") or "").strip()
    date = str(data.get("date") or "").strip()
    if not row or not title or not link:
        return None
    return {"row": row, "title": title, "link": link, "date": date}


def _apply_recipe(spec: SourceSpec, html: str, base_url: str, recipe: dict) -> list[RawNotice]:
    """레시피(row/title/link/date 셀렉터)를 HTML 에 결정론적으로 적용한다."""
    row_sel = str(recipe.get("row") or "").strip()
    title_sel = str(recipe.get("title") or "").strip()
    link_sel = str(recipe.get("link") or "").strip()
    date_sel = str(recipe.get("date") or "").strip()
    if not row_sel or not title_sel or not link_sel:
        return []

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001
        log.debug("html parse failed: %r", exc)
        return []

    try:
        rows = soup.select(row_sel)
    except Exception as exc:  # noqa: BLE001 - 잘못된 셀렉터 문법 방어.
        log.debug("invalid row selector %r: %r", row_sel, exc)
        return []

    items: list[RawNotice] = []
    for row in rows:
        if not isinstance(row, Tag):
            continue

        try:
            title_node = row.select_one(title_sel)
        except Exception:  # noqa: BLE001
            title_node = None
        title = first_text(title_node)

        try:
            link_node = row.select_one(link_sel)
        except Exception:  # noqa: BLE001
            link_node = None
        href = link_node.get("href") if isinstance(link_node, Tag) else None
        url = safe_href(href, base_url)

        posted_at = None
        if date_sel:
            try:
                date_node = row.select_one(date_sel)
            except Exception:  # noqa: BLE001
                date_node = None
            posted_at = first_text(date_node) or None
        if not posted_at:
            posted_at = find_row_date(row)

        notice = make_notice(site_id=spec.id, title=title, url=url, posted_at=posted_at)
        if notice is None:
            continue
        items.append(notice)
        if len(items) >= _MAX_ITEMS:
            break

    return items
