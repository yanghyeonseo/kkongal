"""generic 파이프라인의 공유 계약(타입) — 전략 모듈과 오케스트레이터가 함께 쓴다.

ORM(NoticeSource)에 직접 의존하지 않도록 ``SourceSpec`` 로 필요한 필드만 떼어낸다.
그래서 각 전략과 그 단위 테스트는 DB 없이 순수 함수로 검증할 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from ..schemas import RawNotice


@dataclass
class CapturedResponse:
    """browser 렌더 중 가로챈 XHR/fetch 응답(사이트 내부 JSON API 후보)."""

    url: str
    content_type: str
    json: Any


@dataclass
class FetchResult:
    """fetch 계단이 반환하는 표준 결과. 어떤 백엔드로 가져왔든 형태가 같다."""

    url: str                         # 리다이렉트까지 따라간 최종 URL
    status: int
    text: str = ""                   # HTML/텍스트 본문(JSON 이면 raw 문자열)
    content_type: str = ""
    via: str = "http"                # http | impersonate | browser
    json: Any = None                 # content-type 이 JSON 이면 파싱 결과
    captured_json: list[CapturedResponse] = field(default_factory=list)
    blocked: bool = False            # WAF/anti-bot 차단 신호(403/429/challenge)
    auth_required: bool = False      # 로그인/페이월 경계(로그인 필요 시 여기서 멈춘다)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.blocked and bool(self.text or self.json)


@dataclass
class SourceSpec:
    """generic 파이프라인이 한 소스를 크롤하는 데 필요한 최소 정보."""

    id: str                          # RawNotice.source_id 로 쓰는 토큰(예: "src-42")
    url: str
    name: str = ""
    render: str = "http"             # 마지막으로 성공한 fetch 백엔드(없으면 http)
    scraper_kind: str = ""           # 마지막으로 성공한 추출 전략
    extraction_profile: Optional[dict] = None  # 학습된 레시피(전략별 형태 다름)


# fetch 계단 호출 시그니처. render 를 명시하면 그 백엔드로 강제, 없으면 http→impersonate→
# browser 로 자동 승격한다. want_browser_json=True 면 browser 단계에서 XHR JSON 을 수집한다.
Fetcher = Callable[..., FetchResult]


@dataclass
class StrategyOutcome:
    """한 추출 전략의 결과. items 가 비면 '이 전략은 해당 안 됨/실패' 를 뜻한다.

    orchestrator 는 items 가 있는 첫 전략에서 멈추고, kind/profile/render 를
    NoticeSource 에 저장해 다음 크롤에서 재사용한다.
    """

    kind: str                                    # rss | json_api | heuristic | llm_profile
    items: list[RawNotice] = field(default_factory=list)
    profile: Optional[dict] = None               # NoticeSource.extraction_profile 로 저장
    render: Optional[str] = None                 # 이 전략이 요구한 fetch 백엔드(있으면)
    note: str = ""                               # 진단용(왜 실패/성공했는지)

    @property
    def applied(self) -> bool:
        return bool(self.items)


class Strategy(Protocol):
    """추출 전략 시그니처. 각 모듈이 이 형태의 ``extract`` 함수를 제공한다."""

    def __call__(self, spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome: ...
