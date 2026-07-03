"""generic 추출 전략들. 각 모듈은 다음 시그니처의 ``extract`` 를 제공한다:

    extract(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome

오케스트레이터가 rss → json_api → heuristic → llm_profile 순으로 호출하며,
items 가 있는 첫 전략에서 멈춘다.
"""
