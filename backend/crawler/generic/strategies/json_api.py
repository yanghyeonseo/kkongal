"""내부 JSON API 전략(insane-search Phase 3 차용).

SPA 게시판 상당수는 화면을 그리는 내부 JSON 목록 API를 갖고 있다. 이 전략은:

  1. 학습된 프로필(``extraction_profile["endpoint"]``)이 있으면 그 API를 바로 호출해
     저장된 ``list_path``/``fields`` 로 매핑한다(discovery 생략).
  2. 없으면 browser 로 페이지를 렌더링하며 가로챈 XHR/fetch JSON 들 중에서 공지 목록처럼
     생긴 배열을 찾아내고, 필드를 추측해 매핑한 뒤 다음 크롤을 위한 프로필을 저장한다.

실패해도 오케스트레이터가 다음 전략(heuristic/llm_profile)으로 넘어갈 수 있도록
``extract`` 는 절대 예외를 밖으로 던지지 않는다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ...scrapers.base import compact_text, make_notice, safe_href
from ..base import Fetcher, SourceSpec, StrategyOutcome

log = logging.getLogger("crawler.generic.strategies.json_api")

# 대소문자 무시 부분일치로 "제목스러운" 키를 찾는다.
_TITLE_KEYS = ("title", "subject", "headline", "name", "tit")
# 대소문자 무시 부분일치로 "링크/식별자스러운" 키를 찾는다.
_LINK_KEYS = ("url", "link", "href", "articleid", "id", "seq", "idx", "no")
_DATE_KEYS = ("date", "day", "time", "reg", "created", "posted", "wrtdt")
_SUMMARY_KEYS = ("summary", "desc", "content", "excerpt", "body", "cn")

_MAX_ITEMS = 50


def extract(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome:
    """내부 JSON API 전략 진입점. 실패해도 예외를 던지지 않고 빈 outcome을 돌려준다."""
    try:
        profile = spec.extraction_profile or {}
        endpoint = profile.get("endpoint")
        if endpoint:
            # 학습된 레시피가 있으면 discovery 없이 바로 그 API를 재사용한다.
            return _extract_fast_path(spec, fetch, profile, endpoint)
        return _extract_discovery(spec, fetch)
    except Exception as exc:  # noqa: BLE001 - 이 전략의 실패가 오케스트레이터를 죽이면 안 된다.
        log.debug("json_api extract failed for %s: %r", spec.url, exc)
        return StrategyOutcome(kind="json_api", items=[], note=f"error: {exc!r}")


# -- fast path (학습된 프로필 재사용) -----------------------------------------------


def _extract_fast_path(
    spec: SourceSpec, fetch: Fetcher, profile: dict, endpoint: str
) -> StrategyOutcome:
    result = fetch(endpoint)
    if not result or result.json is None:
        return StrategyOutcome(kind="json_api", items=[], note="fast-path: endpoint returned no JSON")

    list_path = profile.get("list_path")
    fields = profile.get("fields") or {}
    array = _resolve_path(result.json, list_path)
    if not array:
        return StrategyOutcome(kind="json_api", items=[], note="fast-path: list_path not found")

    items = _map_items(spec, array, fields)
    if not items:
        return StrategyOutcome(kind="json_api", items=[], note="fast-path: no valid items")

    return StrategyOutcome(
        kind="json_api",
        items=items,
        profile={"endpoint": endpoint, "list_path": list_path, "fields": fields},
        render=result.via,
    )


def _resolve_path(payload: Any, path: Optional[str]) -> Optional[list]:
    """dot 표기 경로("data.items")로 payload 안의 배열을 찾는다. "[list]" 는 최상위 배열."""
    if not path or path == "[list]":
        return payload if isinstance(payload, list) else None
    node = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, list) else None


# -- discovery (browser 렌더 + XHR JSON 캡처) --------------------------------------


def _extract_discovery(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome:
    result = fetch(spec.url, render="browser", want_browser_json=True)
    if not result:
        return StrategyOutcome(kind="json_api", items=[], note="no fetch result")

    # (api_url, list_of_dicts, list_path, notice_score)
    candidates: list[tuple[str, list, str, int]] = []

    def consider(api_url: str, payload: Any) -> None:
        array, list_path = _find_notice_list(payload)
        if array:
            candidates.append((api_url, array, list_path or "[list]", _notice_score(array)))

    for captured in result.captured_json or []:
        consider(captured.url, captured.json)
    if result.json is not None:
        consider(result.url, result.json)

    if not candidates:
        return StrategyOutcome(kind="json_api", items=[], note="no notice-like JSON list found")

    api_url, array, list_path, _score = max(candidates, key=lambda c: c[3])

    fields = _guess_fields(array)
    items = _map_items(spec, array, fields)
    if not items:
        return StrategyOutcome(
            kind="json_api", items=[], note="notice-like list found but no valid items"
        )

    return StrategyOutcome(
        kind="json_api",
        items=items,
        profile={"endpoint": api_url, "list_path": list_path, "fields": fields},
        render="browser",
    )


def _find_notice_list(payload: Any) -> tuple[Optional[list], Optional[str]]:
    """payload 트리를 재귀 탐색해 공지스러운 dict 배열 중 가장 유력한 것을 찾는다."""
    best: Optional[tuple[str, list, int]] = None

    def walk(node: Any, path: str) -> None:
        nonlocal best
        if isinstance(node, list):
            if node and all(isinstance(x, dict) for x in node):
                score = _notice_score(node)
                if score > 0 and (best is None or score > best[2]):
                    best = (path or "[list]", node, score)
        elif isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(value, child_path)

    walk(payload, "")
    if best is None:
        return None, None
    return best[1], best[0]


def _notice_score(items: list) -> int:
    return sum(1 for item in items if _looks_notice_like(item))


def _looks_notice_like(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    keys = [str(k).lower() for k in item.keys()]
    has_title = any(any(t in k for t in _TITLE_KEYS) for k in keys)
    has_link = any(any(l in k for l in _LINK_KEYS) for k in keys)
    return has_title and has_link


def _guess_fields(array: list) -> dict:
    """배열 안 dict 들의 키를 훑어 title/url/date/summary 로 쓸 만한 키를 추측한다."""
    keys: list[str] = []
    seen: set[str] = set()
    for item in array:
        if not isinstance(item, dict):
            continue
        for k in item.keys():
            key = str(k)
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return {
        "title": _pick_key(keys, _TITLE_KEYS),
        "url": _pick_key(keys, _LINK_KEYS),
        "date": _pick_key(keys, _DATE_KEYS),
        "summary": _pick_key(keys, _SUMMARY_KEYS),
    }


def _pick_key(keys: list[str], candidates: tuple[str, ...]) -> Optional[str]:
    for cand in candidates:
        for k in keys:
            if cand in k.lower():
                return k
    return None


# -- 필드 매핑 --------------------------------------------------------------------


def _map_items(spec: SourceSpec, array: list, fields: dict) -> list:
    title_key = fields.get("title")
    url_key = fields.get("url")
    date_key = fields.get("date")
    summary_key = fields.get("summary")
    if not title_key or not url_key:
        return []

    items = []
    for raw in array:
        if not isinstance(raw, dict):
            continue
        title = raw.get(title_key)
        if not isinstance(title, str) or not title.strip():
            continue
        url = _resolve_item_url(spec, raw.get(url_key))
        if not url:
            continue
        posted_at_raw = raw.get(date_key) if date_key else None
        summary_raw = raw.get(summary_key) if summary_key else None
        notice = make_notice(
            site_id=spec.id,
            title=title,
            url=url,
            posted_at=compact_text(str(posted_at_raw)) if posted_at_raw else None,
            summary=compact_text(str(summary_raw)) if summary_raw else None,
        )
        if notice:
            items.append(notice)
        if len(items) >= _MAX_ITEMS:
            break
    return items


def _resolve_item_url(spec: SourceSpec, raw_value: Any) -> Optional[str]:
    """값이 절대 URL 이 아니면 경로/쿼리 흔적이 있을 때만 origin 기준으로 이어붙인다.

    순수 id(예: 555) 처럼 재구성 규칙이 없는 값은 잘못된 URL 을 만들 위험이 있으므로
    포기한다(해당 항목은 skip).
    """
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return text
    if "/" in text or text.startswith("?"):
        return safe_href(text, spec.url)
    return None
