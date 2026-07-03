"""게시일 문자열 파서 — Django 비의존.

스크래퍼는 사이트마다 제각각인 게시일 문자열(``2026/7/01``, ``2026-07-02``,
``2026.06.23 12:00:00``, ISO, 그리고 사람인처럼 ``6일 전 등록`` 같은 상대표현)을
``RawNotice.posted_at`` 에 담아 넘긴다. 이 모듈은 그 문자열을 ``datetime`` 으로
바꾸는 단일 진입점이다.

- ``repository.parse_notice_datetime`` 이 저장 시 이 파서를 써서 tz-aware 로 만든다.
- ``service.crawl_recent`` 가 7일 필터링을 위해 이 파서를 그대로 재사용한다.

Django 를 import 하지 않으므로 서비스/스크래퍼 어디서든 안전하게 가져다 쓸 수 있다.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from dateutil import parser as _dateutil_parser

# "6일 전", "17시간 전", "3분 전", "2주 전", "1개월 전", "1년 전" 등.
_RELATIVE_UNIT_RE = re.compile(r"(\d+)\s*(분|시간|일|주|개월|달|년)\s*전")


def parse_relative_korean(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """한국어 상대 시각 표현을 절대 ``datetime`` 으로 변환한다.

    대응: 방금/조금 전, 오늘, 어제, 그제(그저께), 그리고 ``N(분|시간|일|주|개월|달|년) 전``.
    매칭되지 않으면 ``None`` — 절대 형식은 :func:`parse_flexible` 이 이어서 처리한다.
    """
    if not text:
        return None
    now = now or datetime.now()
    t = text.strip()

    if "방금" in t or "조금 전" in t:
        return now
    if "그저께" in t or "그제" in t:
        return now - timedelta(days=2)
    if "어제" in t:
        return now - timedelta(days=1)
    if "오늘" in t:
        return now

    match = _RELATIVE_UNIT_RE.search(t)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "분":
        return now - timedelta(minutes=amount)
    if unit == "시간":
        return now - timedelta(hours=amount)
    if unit == "일":
        return now - timedelta(days=amount)
    if unit == "주":
        return now - timedelta(weeks=amount)
    if unit in ("개월", "달"):
        return now - timedelta(days=30 * amount)
    if unit == "년":
        return now - timedelta(days=365 * amount)
    return None


def parse_flexible(value: Optional[str], *, now: Optional[datetime] = None) -> Optional[datetime]:
    """게시일 문자열을 ``datetime`` 으로 파싱한다(상대표현 우선, 이후 절대 형식).

    반환 datetime 은 naive 이거나 (ISO 처럼 offset 이 있으면) aware 일 수 있다.
    파싱 실패 시 ``None`` — 호출부가 알아서 폴백한다.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None

    relative = parse_relative_korean(text, now=now)
    if relative is not None:
        return relative

    # 절대 형식: 2026/7/01, 2026-07-02, 2026.06.23 12:00:00, ISO 등은 dateutil 이 처리.
    # fuzzy=False 를 먼저 시도해 오탐을 줄이고, 실패 시에만 fuzzy 로 관대하게 재시도.
    for fuzzy in (False, True):
        try:
            return _dateutil_parser.parse(text, fuzzy=fuzzy)
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def to_naive(value: Optional[datetime]) -> Optional[datetime]:
    """aware/naive 가 섞인 datetime 을 naive 로 정규화한다(로컬 wall-clock 기준).

    7일 윈도우 비교처럼 서로 다른 소스의 datetime 을 한 축에서 비교할 때 쓴다.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value
