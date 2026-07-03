"""임의 사이트(카탈로그에 손파서가 없는 URL)를 자동 수집하는 generic 파이프라인.

insane-search(github.com/fivetaku/insane-search)의 계단식 접근을 차용한다:
비용이 싼 전략부터 시도하고, 막히면(blocked/0건) 다음 단계로 승격한다.

  fetch 계단(fetcher.py):  http(httpx) → impersonate(curl_cffi TLS 위장) → browser(playwright)
  추출 계단(orchestrator):  rss → json_api → heuristic → llm_profile

성공한 전략과 학습 결과는 ``NoticeSource.scraper_kind`` / ``extraction_profile`` /
``render`` 로 저장돼 다음 크롤부터 곧바로 재사용된다.
"""
from __future__ import annotations

from .base import CapturedResponse, FetchResult, SourceSpec, StrategyOutcome

__all__ = [
    "CapturedResponse",
    "FetchResult",
    "SourceSpec",
    "StrategyOutcome",
]
