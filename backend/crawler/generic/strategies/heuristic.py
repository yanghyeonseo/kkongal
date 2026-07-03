"""휴리스틱 반복-블록 HTML 목록 추출 전략.

공지 목록 페이지는 대개 "행" 이 반복되는 지배적인 구조를 가진다 — 각 행은 앵커
(제목+링크) 하나와, 종종 날짜 하나를 포함한다. 이 전략은 사이트별 셀렉터 없이
그 반복 구조를 스스로 찾아낸다.

1) ``spec.extraction_profile`` 에 학습된 ``row`` 셀렉터가 있으면 바로 재사용(fast-path).
2) 없으면 table/ul/ol/div 후보 반복 그룹을 모아 "유효한 행(링크+제목)" 개수로
   점수화하고, 임계치(``MIN_ROWS``) 이상인 것 중 최고 점수 그룹을 고른다.
3) 고른 그룹의 셀렉터를 ``profile`` 에 저장해 다음 크롤에서 재사용하게 한다.
"""
from __future__ import annotations

import logging
from typing import Optional

from bs4 import BeautifulSoup, Tag

from ...scrapers.base import find_row_date, first_text, make_notice, safe_href, take
from ..base import Fetcher, SourceSpec, StrategyOutcome

log = logging.getLogger("crawler.generic.heuristic")

MIN_ROWS = 3          # 이 이상 유효 행이 있어야 "목록"으로 인정한다(네비게이션 오탐 방지).
MAX_ITEMS = 50


def extract(spec: SourceSpec, fetch: Fetcher) -> StrategyOutcome:
    """반복 블록 구조를 탐지해 공지 목록을 뽑는다. 실패해도 예외를 밖으로 던지지 않는다."""
    try:
        result = fetch(spec.url)
    except Exception as exc:  # noqa: BLE001 - fetch 실패는 이 전략의 실패일 뿐.
        log.debug("heuristic fetch 실패 %s: %r", spec.url, exc)
        return StrategyOutcome(kind="heuristic", items=[], note=f"fetch 실패: {exc!r}")

    if not result.ok or not result.text:
        return StrategyOutcome(kind="heuristic", items=[], note="fetch 결과가 비어있거나 실패함")

    try:
        soup = BeautifulSoup(result.text, "lxml")
    except Exception as exc:  # noqa: BLE001
        return StrategyOutcome(kind="heuristic", items=[], note=f"HTML 파싱 실패: {exc!r}")

    base_url = result.url

    # -- fast-path: 이미 학습된 행 셀렉터가 있으면 바로 재사용 --------------------
    profile = spec.extraction_profile or {}
    row_selector = profile.get("row") if isinstance(profile, dict) else None
    if row_selector:
        try:
            rows = soup.select(row_selector)
        except Exception:  # noqa: BLE001 - 저장된 셀렉터가 더 이상 유효하지 않으면 폴백.
            rows = []
        if rows:
            items = _extract_rows(rows, base_url, spec.id)
            if items:
                return StrategyOutcome(
                    kind="heuristic",
                    items=take(items, MAX_ITEMS),
                    profile={"row": row_selector},
                    note=f"fast-path 셀렉터 재사용: {row_selector}",
                )

    # -- discovery: 후보 반복 그룹을 모아 점수화 -------------------------------
    best_selector: Optional[str] = None
    best_rows: list[Tag] = []
    best_score = (0, 0)
    for selector, rows in _iter_candidates(soup):
        score = _score_rows(rows, base_url)
        if score[0] < MIN_ROWS:
            continue
        if score > best_score:
            best_score = score
            best_selector = selector
            best_rows = rows

    if not best_selector:
        return StrategyOutcome(kind="heuristic", items=[], note="반복되는 목록 구조를 찾지 못함")

    items = _extract_rows(best_rows, base_url, spec.id)
    if not items:
        return StrategyOutcome(kind="heuristic", items=[], note="후보 그룹은 찾았지만 유효 항목이 없음")

    return StrategyOutcome(
        kind="heuristic",
        items=take(items, MAX_ITEMS),
        profile={"row": best_selector},
        note=f"휴리스틱 탐지: {best_selector} (유효 {best_score[0]}행, 날짜 {best_score[1]}행)",
    )


# -- 후보 탐색 ------------------------------------------------------------------


def _iter_candidates(soup: BeautifulSoup) -> list[tuple[str, list[Tag]]]:
    """(재사용 가능한 CSS 셀렉터, 행 리스트) 후보들을 모은다."""
    candidates: list[tuple[str, list[Tag]]] = []

    for table in soup.find_all("table"):
        tbody = table.find("tbody")
        if tbody is not None:
            rows = tbody.find_all("tr", recursive=False)
            selector = "table tbody tr"
        else:
            rows = table.find_all("tr", recursive=False)
            selector = "table tr"
        if len(rows) >= MIN_ROWS:
            candidates.append((selector, rows))

    for tag_name in ("ul", "ol"):
        for container in soup.find_all(tag_name):
            rows = container.find_all("li", recursive=False)
            if len(rows) < MIN_ROWS:
                continue
            cls = _stable_class(container)
            selector = f"{tag_name}.{cls} li" if cls else f"{tag_name} li"
            candidates.append((selector, rows))

    for container in soup.find_all("div"):
        rows = container.find_all("div", recursive=False)
        if len(rows) < MIN_ROWS:
            continue
        container_cls = _stable_class(container)
        row_cls = _stable_class(rows[0]) if rows else None
        if container_cls and row_cls:
            selector = f"div.{container_cls} > div.{row_cls}"
        elif container_cls:
            selector = f"div.{container_cls} > div"
        else:
            selector = "div > div"
        candidates.append((selector, rows))

    return candidates


def _stable_class(tag: Tag) -> Optional[str]:
    """태그의 첫 클래스를 셀렉터에 쓸 안정적인 힌트로 사용한다(없으면 None)."""
    for cls in tag.get("class") or []:
        if cls:
            return cls
    return None


# -- 점수화 / 추출 ---------------------------------------------------------------


def _row_anchor(row: Tag, base_url: str) -> Optional[Tag]:
    """행 안에 ``safe_href`` 로 유효한 앵커가 '정확히 하나'일 때만 그 앵커를 반환한다.

    앵커가 없거나 여러 개면(내비게이션 메뉴, 레이아웃 섹션 등 진짜 "행"이 아닐 가능성이
    큼) None 을 돌려줘 오탐(false positive)을 줄인다.
    """
    valid = [a for a in row.find_all("a", href=True) if safe_href(a.get("href"), base_url)]
    if len(valid) != 1:
        return None
    return valid[0]


def _score_rows(rows: list[Tag], base_url: str) -> tuple[int, int]:
    """(유효 행 수, 그중 날짜가 있는 행 수). 높을수록 좋은 후보."""
    valid = 0
    dated = 0
    for row in rows:
        anchor = _row_anchor(row, base_url)
        if anchor is None:
            continue
        if len(first_text(anchor)) < 2:
            continue
        valid += 1
        if find_row_date(row):
            dated += 1
    return valid, dated


def _extract_rows(rows: list[Tag], base_url: str, site_id: str) -> list:
    out = []
    for row in rows:
        anchor = _row_anchor(row, base_url)
        if anchor is None:
            continue
        title = first_text(anchor)
        url = safe_href(anchor.get("href"), base_url)
        posted_at = find_row_date(row)
        notice = make_notice(site_id=site_id, title=title, url=url, posted_at=posted_at)
        if notice:
            out.append(notice)
    return out
