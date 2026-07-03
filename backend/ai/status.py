"""AI 가용 상태(정상 / 사용량 소진 / 키 미설정) 신호.

프론트엔드가 "AI 사용량이 소진돼 키워드 기반으로 임시 동작 중" 배너를 띄울 수 있도록,
LLM 호출이 429(사용량/레이트리밋)로 폴백 전환되면 플래그를 남기고, 성공하면 지운다.

캐시(기본 LocMemCache)는 프로세스 지역이라, sync 엔드포인트(웹 프로세스)에서 발생한
429 는 같은 웹 프로세스의 상태 조회에 바로 반영된다. 사용자의 주요 흐름(동기화 버튼 →
429 → 배너)에는 충분하다. 키 미설정은 settings 로 즉시 판정한다.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

_KEY = "ai:degraded_reason"
_TTL = 60 * 30  # 30분 뒤 자동 만료(할당량은 대개 그 안에 회복)


def mark_degraded(reason: str = "quota") -> None:
    try:
        cache.set(_KEY, reason, _TTL)
    except Exception:  # 캐시 문제로 본 흐름을 막지 않는다
        pass


def mark_ok() -> None:
    try:
        cache.delete(_KEY)
    except Exception:
        pass


def get_status() -> dict:
    """{degraded: bool, reason: 'quota'|'disabled'|'ok', message: str}."""
    if not getattr(settings, "LLM_API_KEY", ""):
        return {
            "degraded": True,
            "reason": "disabled",
            "message": "AI 키가 설정되지 않아 키워드 기반으로 동작 중이에요.",
        }
    try:
        reason = cache.get(_KEY)
    except Exception:
        reason = None
    if reason == "quota":
        return {
            "degraded": True,
            "reason": "quota",
            "message": "AI 사용량이 일시적으로 소진돼 키워드 기반으로 임시 동작 중이에요. 잠시 후 자동으로 정상화됩니다.",
        }
    return {"degraded": False, "reason": "ok", "message": ""}
