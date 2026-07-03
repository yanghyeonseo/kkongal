"""generic 추출 계단식 오케스트레이터.

한 소스에 대해 rss → json_api → heuristic → llm_profile 순으로 전략을 시도하고,
공지를 뽑은 첫 전략에서 멈춘다. 이미 학습된 전략(``spec.scraper_kind`` +
``extraction_profile``)이 있으면 그 전략을 먼저 시도해 재크롤 비용을 아낀다.

목록만으로는 DB Notice 의 content/published_at 이 비므로, 뽑은 항목을 metadata.hydrate
로 상세 페이지 OGP/JSON-LD/meta 를 훑어 채운 뒤 반환한다.
"""
from __future__ import annotations

import logging
from typing import Callable

from ..schemas import RawNotice
from . import metadata
from .base import Fetcher, SourceSpec, StrategyOutcome
from .strategies import heuristic, json_api, llm_selector, rss

log = logging.getLogger("crawler.generic")

# (kind, extract) 순서 = 계단식 순서. kind 는 NoticeSource.scraper_kind 값과 일치.
# 비용 오름차순으로 배치한다: rss(http) → heuristic(http) → json_api(headless browser) →
# llm_profile(LLM 호출). json_api 는 사이트 내부 API 를 캡처하려 브라우저를 띄우므로,
# http 로 끝나는 heuristic 보다 뒤에 둬 정적 게시판이 브라우저 비용을 물지 않게 한다.
_LADDER: list[tuple[str, Callable[[SourceSpec, Fetcher], StrategyOutcome]]] = [
    ("rss", rss.extract),
    ("heuristic", heuristic.extract),
    ("json_api", json_api.extract),
    ("llm_profile", llm_selector.extract),
]

# 상세 페이지 보강(metadata.hydrate)으로 방문할 최대 항목 수(비용 상한).
_HYDRATE_CAP = 15


def _ordered_strategies(spec: SourceSpec):
    """학습된 전략이 있으면 그것을 맨 앞으로 당겨 우선 시도한다."""
    ladder = list(_LADDER)
    if spec.scraper_kind and spec.extraction_profile:
        ladder.sort(key=lambda pair: pair[0] != spec.scraper_kind)
    return ladder


def _bind_fetch(fetch: Fetcher, spec: SourceSpec) -> Fetcher:
    """학습된 render 가 browser/impersonate 면 그 tier 로 바로 가도록 fetch 를 감싼다.

    첫 크롤(scraper_kind 미학습)이나 http 소스는 감싸지 않는다 — render 를 강제하면
    http→impersonate→browser 자동 승격이 막혀 SPA 첫 탐색이 실패할 수 있기 때문. 학습이
    끝나 browser 가 확정된 소스만 재크롤 시 값비싼 재승격을 건너뛴다(호출자가 render 를
    명시하면 그 값이 우선한다 — 예: json_api 의 want_browser_json).
    """
    forced = spec.render if (spec.scraper_kind and spec.render not in ("", "http")) else None
    if not forced:
        return fetch

    def bound(url, *, render=None, want_browser_json=False):
        return fetch(url, render=render or forced, want_browser_json=want_browser_json)

    return bound


def scrape(spec: SourceSpec, fetch: Fetcher, *, limit: int = 50) -> StrategyOutcome:
    """계단식으로 공지를 추출하고 상세 보강까지 마친 StrategyOutcome 을 반환한다.

    어떤 전략도 항목을 못 뽑으면 items=[] 인 outcome(kind="")을 돌려준다. 예외는
    전략 안에서 삼켜지지만, 방어적으로 여기서도 한 번 더 감싼다.
    """
    bound_fetch = _bind_fetch(fetch, spec)
    for kind, extract in _ordered_strategies(spec):
        try:
            outcome = extract(spec, bound_fetch)
        except Exception as exc:  # noqa: BLE001 - 한 전략 실패가 계단을 죽이지 않게.
            log.debug("generic strategy %s raised for %s: %r", kind, spec.url, exc)
            continue
        if outcome and outcome.applied:
            outcome.items = outcome.items[:limit]
            try:
                metadata.hydrate(outcome.items, bound_fetch, cap=_HYDRATE_CAP)
            except Exception:  # noqa: BLE001 - 보강 실패는 목록 자체를 버리지 않는다.
                log.debug("metadata hydrate failed for %s", spec.url, exc_info=True)
            log.info(
                "generic %s: %s → %d items (via %s)",
                kind, spec.url, len(outcome.items), outcome.render or spec.render or "http",
            )
            return outcome

    return StrategyOutcome(kind="", items=[], note="no strategy matched")
