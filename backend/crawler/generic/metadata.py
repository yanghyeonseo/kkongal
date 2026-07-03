"""상세 페이지 메타데이터 하이드레이션 — 목록에서 얻은 ``RawNotice`` 의 빈 칸을 채운다.

리스트 전략은 대부분 title+url(그리고 가끔 posted_at)만 얻는다. DB 의 content/
published_at/summary 컬럼을 채우려면 각 항목의 상세 페이지를 방문해 OGP, JSON-LD,
meta 태그, 본문 셀렉터 순으로 값을 뽑아야 한다. 이 모듈이 그 일을 한다.

임의의 외부 사이트 HTML 을 다루므로 전 구간 방어적으로 작성한다 — 파싱 실패, 잘못된
구조, 네트워크 실패 어느 것도 파이프라인 전체를 죽이면 안 된다.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from bs4 import BeautifulSoup

from ..schemas import RawNotice
from ..scrapers.base import compact_text, extract_body_text, extract_meta_content
from .base import Fetcher

log = logging.getLogger("crawler.generic.metadata")

# JSON-LD 블록 중 "기사"로 볼 @type 들(우선순위용, 소문자 비교).
_ARTICLE_TYPES = {"article", "newsarticle", "blogposting"}

# hydrate() 기본 본문 셀렉터 — 흔한 게시판/기사 레이아웃을 폭넓게 커버한다.
_DEFAULT_BODY_SELECTORS = [
    "article",
    ".content",
    ".view-content",
    ".board-view",
    ".post-content",
    "#content",
    "main",
    ".entry-content",
]

# summary/description 폴백에 쓰는 meta 이름 후보(og: 접두어 없는 일반 meta 포함).
_DESCRIPTION_META_NAMES = ["description", "og:description", "twitter:description"]
# posted_at 폴백에 쓰는 meta 이름 후보(OGP 가 아닌 순수 meta 태그).
_POSTED_AT_META_NAMES = ["article:published_time", "date", "pubdate"]


def extract_ogp(html: str) -> dict:
    """Open Graph 메타 태그를 ``og:`` 접두어를 뗀 dict 로 반환한다.

    ``<meta property="og:*">`` 와 ``<meta name="og:*">`` 둘 다 읽는다(사이트마다
    property/name 을 섞어 쓰는 경우가 있어서). 같은 키가 여러 번 나오면 처음 값을 쓴다.
    """
    out: dict = {}
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001 - 파싱 실패는 빈 dict 로 흡수.
        log.debug("ogp html parse failed: %r", exc)
        return out

    for meta in soup.select("meta[content]"):
        key = (meta.get("property") or meta.get("name") or "").strip().lower()
        if not key.startswith("og:"):
            continue
        prop = key[len("og:"):]
        if not prop or prop in out:
            continue
        content = compact_text(meta.get("content"))
        if content:
            out[prop] = content
    return out


def extract_jsonld(html: str) -> list[dict]:
    """``<script type="application/ld+json">`` 블록들을 파싱해 평평한 dict 목록으로 만든다.

    사이트마다 단일 객체, 배열, ``@graph`` 로 감싼 형태를 섞어 쓰므로 모두 평탄화한다.
    한 스크립트 블록이 깨진 JSON 이어도 그 블록만 건너뛰고 나머지는 계속 처리한다.
    """
    out: list[dict] = []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001
        log.debug("jsonld html parse failed: %r", exc)
        return out

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string
        if raw is None:
            raw = script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 - 깨진 JSON-LD 는 조용히 건너뛴다.
            log.debug("jsonld json parse failed: %r", exc)
            continue
        _flatten_jsonld(data, out)
    return out


def _flatten_jsonld(data: Any, out: list[dict]) -> None:
    """JSON-LD 값을 재귀적으로 평탄화해 dict 만 ``out`` 에 쌓는다."""
    if isinstance(data, list):
        for item in data:
            _flatten_jsonld(item, out)
        return
    if not isinstance(data, dict):
        return
    graph = data.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            _flatten_jsonld(item, out)
        return
    out.append(data)


def article_fields_from_jsonld(blocks: list[dict]) -> dict:
    """JSON-LD 블록들에서 기사 관련 필드를 뽑는다.

    Article/NewsArticle/BlogPosting ``@type`` 을 우선하고, 같은 필드가 여러 블록에
    있으면 먼저 채워진 값을 유지한다.
    """

    def _type_names(block: dict) -> set:
        t = block.get("@type")
        if isinstance(t, list):
            return {str(x).lower() for x in t}
        if t:
            return {str(t).lower()}
        return set()

    try:
        ordered = sorted(blocks, key=lambda b: 0 if _type_names(b) & _ARTICLE_TYPES else 1)
    except Exception as exc:  # noqa: BLE001 - 정렬 실패해도 원래 순서로 계속.
        log.debug("jsonld sort failed: %r", exc)
        ordered = list(blocks)

    out: dict = {}
    for block in ordered:
        if not isinstance(block, dict):
            continue

        headline = block.get("headline") or block.get("name")
        if headline and "headline" not in out:
            out["headline"] = compact_text(str(headline))

        body = block.get("articleBody") or block.get("description")
        if body and "articleBody" not in out:
            out["articleBody"] = compact_text(str(body))

        published = block.get("datePublished")
        if published and "datePublished" not in out:
            out["datePublished"] = compact_text(str(published))

        modified = block.get("dateModified")
        if modified and "dateModified" not in out:
            out["dateModified"] = compact_text(str(modified))

        dateline = block.get("dateline")
        if dateline and "dateline" not in out:
            out["dateline"] = compact_text(str(dateline))

    return out


def hydrate(
    items: list[RawNotice],
    fetch: Fetcher,
    *,
    cap: int = 15,
    body_selectors: Optional[list[str]] = None,
) -> list[RawNotice]:
    """상세 페이지를 방문해 각 ``RawNotice`` 의 body/summary/posted_at 빈 칸을 채운다.

    이미 값이 있는 필드는 절대 덮어쓰지 않는다. ``body`` 가 이미 있는 항목은 fetch
    자체를 건너뛴다. body 가 없는 항목 중 최대 ``cap`` 개까지만 처리하고, 그 이후
    항목은 손대지 않고 그대로 둔다. 항목 하나의 실패(네트워크/파싱)는 로그만 남기고
    삼켜서 나머지 항목 처리를 막지 않는다.
    """
    selectors = body_selectors or list(_DEFAULT_BODY_SELECTORS)
    processed = 0
    for item in items:
        if item.body:
            continue
        if processed >= cap:
            break
        processed += 1
        try:
            _hydrate_one(item, fetch, selectors)
        except Exception as exc:  # noqa: BLE001 - 개별 항목 실패가 전체를 죽이면 안 된다.
            log.debug("hydrate failed for %s: %r", item.url, exc)
    return items


def _hydrate_one(item: RawNotice, fetch: Fetcher, selectors: list[str]) -> None:
    result = fetch(str(item.url))
    if result is None or not getattr(result, "ok", False):
        return
    html = result.text
    if not html:
        return

    jsonld_blocks = extract_jsonld(html)
    article = article_fields_from_jsonld(jsonld_blocks)
    ogp = extract_ogp(html)

    if not item.body:
        body = article.get("articleBody")
        if not body:
            body = extract_body_text(html, selectors)
        if not body:
            body = ogp.get("description") or extract_meta_content(html, _DESCRIPTION_META_NAMES)
        if body:
            item.body = body

    if not item.summary:
        summary = ogp.get("description") or extract_meta_content(html, _DESCRIPTION_META_NAMES)
        if summary:
            item.summary = summary

    if not item.posted_at:
        posted = (
            article.get("datePublished")
            or ogp.get("article:published_time")
            or extract_meta_content(html, _POSTED_AT_META_NAMES)
        )
        if posted:
            item.posted_at = posted
