"""RSS/Atom 피드 추출 전략.

추출 계단의 첫 단계 — 사이트가 표준 피드를 제공하면 가장 싸고 안정적으로 목록을
얻을 수 있다. 우선순위:

  1. fast-path : ``spec.extraction_profile["feed"]`` 로 학습된 피드 URL 이 있으면 그걸 바로 fetch.
  2. discovery : ``spec.url`` 자체가 피드인지 확인 → HTML ``<link rel=alternate>`` 탐색
                 → 흔한 경로(``/rss`` 등) 순서로 후보를 fetch 해 본다.

발견한 피드 URL 은 ``profile={"feed": ...}`` 로 반환해 오케스트레이터가 다음 크롤부터
바로 fast-path 를 타게 한다.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import feedparser
from bs4 import BeautifulSoup

from ...scrapers.base import compact_text, make_notice
from ...schemas import RawNotice
from ..base import FetchResult, Fetcher, SourceSpec, StrategyOutcome

log = logging.getLogger("crawler.generic.rss")

# spec.url 에서 피드를 못 찾았을 때 시도해 볼 흔한 경로들.
_COMMON_FEED_PATHS = (
    "/rss",
    "/feed",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
    "/feed.xml",
    "/rss/feed",
)

_MAX_ITEMS = 50


def extract(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome:
    """RSS/Atom 전략 진입점. 이 함수는 절대 예외를 밖으로 던지지 않는다."""
    try:
        return _extract(spec, fetch)
    except Exception as exc:  # noqa: BLE001 - 전략 하나의 실패가 오케스트레이터를 죽이면 안 된다.
        log.debug("rss extract failed for %s: %r", spec.url, exc)
        return StrategyOutcome(kind="rss", items=[], note=f"error: {exc!r}")


def _extract(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome:
    # 1) fast-path: 이전 크롤에서 학습된 피드 URL 이 있으면 discovery 를 건너뛴다.
    profile = spec.extraction_profile or {}
    learned_feed = profile.get("feed")
    if learned_feed:
        parsed = _fetch_and_parse(fetch, learned_feed)
        if parsed is not None and parsed.entries:
            items = _build_items(spec, parsed)
            if items:
                return StrategyOutcome(
                    kind="rss",
                    items=items,
                    profile={"feed": learned_feed},
                    note="fast-path: learned feed",
                )
        # 학습된 피드가 더 이상 유효하지 않으면 아래 discovery 로 폴백한다.

    # 2) discovery: spec.url 자체를 fetch 해서 피드인지, 아니면 피드로 이어지는 힌트가
    #    있는지 확인한다.
    root: Optional[FetchResult] = None
    try:
        root = fetch(spec.url)
    except Exception as exc:  # noqa: BLE001
        log.debug("fetch failed for %s: %r", spec.url, exc)
        root = None

    root_parsed = _try_parse_feed(root)
    if root_parsed is not None and root_parsed.entries:
        items = _build_items(spec, root_parsed)
        if items:
            return StrategyOutcome(
                kind="rss",
                items=items,
                profile={"feed": spec.url},
                note="discovery: url itself is a feed",
            )

    # 3) HTML <link rel=alternate type=application/(rss|atom)+xml> 탐색 후 흔한 경로 폴백.
    candidates: list[str] = []
    if root is not None and root.text:
        candidates.extend(_discover_link_tags(root.text, spec.url))
    candidates.extend(_common_path_candidates(spec.url))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        parsed = _fetch_and_parse(fetch, candidate)
        if parsed is not None and parsed.entries:
            items = _build_items(spec, parsed)
            if items:
                return StrategyOutcome(
                    kind="rss",
                    items=items,
                    profile={"feed": candidate},
                    note=f"discovery: found feed at {candidate}",
                )

    return StrategyOutcome(kind="rss", items=[], note="no feed")


# -- helpers ------------------------------------------------------------------


def _fetch_and_parse(fetch: Fetcher, url: str):
    """url 을 fetch 해서 feedparser 로 파싱한다. 실패하면 None."""
    try:
        result = fetch(url)
    except Exception as exc:  # noqa: BLE001
        log.debug("fetch failed for %s: %r", url, exc)
        return None
    return _try_parse_feed(result)


def _try_parse_feed(result: Optional[FetchResult]):
    """FetchResult 본문을 feedparser 로 파싱한다. 피드가 아니거나 실패하면 None."""
    if result is None or not result.ok:
        return None
    text = result.text
    if not text:
        return None
    try:
        parsed = feedparser.parse(text)
    except Exception as exc:  # noqa: BLE001
        log.debug("feedparser failed for %s: %r", result.url, exc)
        return None
    if not getattr(parsed, "entries", None):
        return None
    return parsed


def _discover_link_tags(html: str, base_url: str) -> list[str]:
    """HTML <head> 의 <link rel="alternate" type="application/rss+xml|atom+xml"> 를 찾는다."""
    out: list[str] = []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001
        log.debug("html parse failed: %r", exc)
        return out

    for link in soup.find_all("link"):
        rel = link.get("rel")
        rels = [r.lower() for r in rel] if isinstance(rel, list) else [str(rel or "").lower()]
        if "alternate" not in rels:
            continue
        type_ = (link.get("type") or "").lower()
        if "rss+xml" not in type_ and "atom+xml" not in type_:
            continue
        href = link.get("href")
        if not href:
            continue
        out.append(urljoin(base_url, href))
    return out


def _common_path_candidates(url: str) -> list[str]:
    """사이트 origin 기준으로 흔히 쓰이는 피드 경로 후보를 만든다."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [urljoin(origin + "/", path.lstrip("/")) for path in _COMMON_FEED_PATHS]


def _build_items(spec: SourceSpec, parsed) -> list[RawNotice]:
    """feedparser 결과의 entries 를 RawNotice 로 변환한다(최대 _MAX_ITEMS 건)."""
    items: list[RawNotice] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", None)
        posted_at = getattr(entry, "published", None) or getattr(entry, "updated", None)
        summary_raw = getattr(entry, "summary", None)
        summary = compact_text(summary_raw) if summary_raw else None

        notice = make_notice(
            site_id=spec.id,
            title=title,
            url=link,
            posted_at=posted_at,
            summary=summary,
        )
        if notice is None:
            continue
        items.append(notice)
        if len(items) >= _MAX_ITEMS:
            break
    return items
