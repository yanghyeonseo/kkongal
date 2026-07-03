"""제공자 비종속(OpenAI 호환) LLM 클라이언트 + 오프라인 키워드 폴백.

`POST {LLM_BASE_URL}/chat/completions` 를 httpx 로 호출한다. 기본 대상은 가성비가
좋은 Google Gemini 의 OpenAI 호환 엔드포인트이지만, LLM_BASE_URL/LLM_MODEL/
LLM_API_KEY 만 바꾸면 OpenAI·DeepSeek·Groq·Together 등 어떤 OpenAI 호환 제공자로도
교체된다.

핵심 안전 장치:
- LLM_API_KEY 가 비어 있거나 API 호출이 실패하면 결코 예외를 밖으로 던지지 않고,
  결정론적 키워드 매칭 폴백으로 전환한다(로그 남김). 덕분에 키 없이도 데모/테스트/CI
  가 그대로 동작한다.
- 응답 JSON 은 방어적으로 파싱한다(코드펜스 제거, 앞뒤 잡텍스트 허용).
- 비용(NFR-6) 통제를 위해 본문을 LLM_MAX_CONTENT_CHARS 로 잘라 보낸다.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from django.conf import settings

from .prompts import build_enrichment_messages, build_messages

logger = logging.getLogger("ai")

# provider 값
PROVIDER_LLM = "llm"
PROVIDER_FALLBACK = "fallback"

# 보강(enrichment)은 공지당 1회뿐이라 분류(사용자당 1회)보다 본문을 넉넉히 보낸다.
# content_markdown 이 원문을 최대한 보존하도록 상한을 크게 잡되, 병적으로 큰 페이지는
# 이 지점에서 잘라 비용/지연을 방어한다.
ENRICH_MAX_CONTENT_CHARS = 8000

# 일시적 과부하(429 Too Many Requests / 503 Service Unavailable, Gemini 무료 티어 등)
# 는 짧게 재시도하면 대개 성공한다. 그래도 실패하면 키워드 폴백으로 넘어간다.
_RETRY_STATUSES = frozenset({429, 503})
_MAX_RETRIES = 2
_RETRY_BACKOFF = 0.6


@dataclass
class Verdict:
    """분류 결과. score 는 항상 0.0~1.0 로 클램프된다."""

    relevant: bool
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    reason: str = ""
    provider: str = PROVIDER_LLM

    def as_dict(self) -> dict[str, Any]:
        return {
            "relevant": self.relevant,
            "score": self.score,
            "matched_keywords": list(self.matched_keywords),
            "reason": self.reason,
        }


@dataclass
class Enrichment:
    """공지 보강 결과(사용자 무관).

    ``deadline`` 은 LLM 이 준 '원문 그대로의' 마감일 문자열(또는 None)이다. aware
    datetime 으로의 파싱·저장은 호출자(ai/enrich.py)가 담당한다.
    """

    summary: str = ""
    content_markdown: str = ""
    deadline: Optional[str] = None
    provider: str = PROVIDER_LLM


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """LLM 텍스트 응답에서 JSON 객체를 방어적으로 추출한다.

    - 앞뒤 공백/코드펜스(```json ... ```) 제거
    - 그래도 실패하면 첫 '{' ~ 마지막 '}' 구간을 잘라 재시도
    실패 시 ValueError.
    """

    if not text or not text.strip():
        raise ValueError("빈 LLM 응답")

    cleaned = text.strip()
    fence = _FENCE_RE.match(cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise ValueError("응답에서 JSON 객체를 찾지 못함")


# 문장 종결 부호(마침표/물음표/느낌표, 한중일 문장부호 포함) 뒤의 공백에서 자른다.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")


def first_sentences(text: str, count: int = 3, *, max_chars: int = 400) -> str:
    """본문 앞부분에서 문장 ``count`` 개를 뽑아 오프라인 요약 폴백으로 쓴다.

    문장 부호가 없으면(목록·표 형태 공지 등) 정규화한 앞부분을 ``max_chars`` 로 잘라
    돌려준다. 결코 예외를 던지지 않는다.
    """

    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return ""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(normalized) if p.strip()]
    summary = " ".join(parts[:count]) if parts else normalized
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "…"
    return summary


class LLMClient:
    """OpenAI 호환 chat/completions 클라이언트.

    설정은 생성자 인자로 덮어쓸 수 있으며, 기본값은 Django settings 에서 읽는다.
    테스트에서는 ``transport`` 에 ``httpx.MockTransport`` 를 주입해 네트워크 없이
    LLM 경로를 검증할 수 있다.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_content_chars: Optional[int] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.api_key = settings.LLM_API_KEY if api_key is None else api_key
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self.timeout = (
            settings.LLM_TIMEOUT_SECONDS if timeout is None else timeout
        )
        self.max_content_chars = (
            settings.LLM_MAX_CONTENT_CHARS
            if max_content_chars is None
            else max_content_chars
        )
        self._transport = transport

    @property
    def enabled(self) -> bool:
        """API 키가 있으면 실제 LLM 호출, 없으면 폴백."""
        return bool(self.api_key)

    def classify(
        self,
        *,
        title: str,
        content: str,
        publisher: str = "",
        profile: Optional[dict[str, Any]] = None,
        interests: Optional[list[dict[str, Any]]] = None,
        summary: str = "",
    ) -> Verdict:
        """공지 + 사용자(프로필/관심조건) 을 받아 관련도 Verdict 를 돌려준다.

        ``summary`` 는 보강 단계에서 만든 3문장 요약(있으면). 모델 입력에 함께 실어
        더 싸고 정확하게 판단하도록 돕는다(NFR-6).
        어떤 경우에도 예외를 밖으로 던지지 않는다(실패 시 키워드 폴백).
        """

        profile = profile or {}
        interests = list(interests or [])
        truncated = (content or "")[: self.max_content_chars]

        if not self.enabled:
            return self._fallback(
                title, truncated, interests, note="LLM_API_KEY 미설정"
            )

        try:
            data = self._call_api(
                title=title,
                content=truncated,
                publisher=publisher,
                profile=profile,
                interests=interests,
                summary=summary,
            )
            return self._parse_verdict(data)
        except Exception as exc:  # 결코 밖으로 던지지 않는다
            logger.warning(
                "LLM 호출/파싱 실패 → 키워드 폴백 전환 (model=%s): %s",
                self.model,
                exc,
            )
            return self._fallback(
                title, truncated, interests, note="LLM 호출 실패"
            )

    # -- 내부 구현 ---------------------------------------------------------

    def _call_api(
        self,
        *,
        title: str,
        content: str,
        publisher: str,
        profile: dict[str, Any],
        interests: list[dict[str, Any]],
        summary: str = "",
    ) -> dict[str, Any]:
        messages = build_messages(
            title=title,
            content=content,
            publisher=publisher,
            profile=profile,
            interests=interests,
            summary=summary,
        )
        return self._chat_json(messages)

    def _chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """messages 를 보내 JSON 객체 응답을 받아 방어적으로 파싱한다.

        분류(classify)와 보강(enrich)이 공유하는 저수준 호출. 일시 과부하
        (429/503)는 짧게 재시도한다. 실패 시 예외를 던지며, 폴백 전환은 각 상위
        메서드(classify/enrich)가 책임진다.
        """

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            # 대부분의 OpenAI 호환 제공자(OpenAI/Gemini/DeepSeek/Groq)가 지원.
            # 미지원 제공자여도 방어적 파서가 백업 역할을 한다.
            "response_format": {"type": "json_object"},
        }
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(
            timeout=self.timeout, transport=self._transport
        ) as client:
            for attempt in range(_MAX_RETRIES + 1):
                response = client.post(url, headers=headers, json=payload)
                if (
                    response.status_code in _RETRY_STATUSES
                    and attempt < _MAX_RETRIES
                ):
                    logger.info(
                        "LLM %s 일시 과부하 → 재시도 %d/%d",
                        response.status_code, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                break
            response.raise_for_status()
            body = response.json()

        content_text = body["choices"][0]["message"]["content"]
        return extract_json(content_text)

    # -- 보강(enrichment) — 사용자 무관, 공지당 1회 -------------------------

    def enrich(self, *, title: str, content: str) -> Enrichment:
        """공지 title+content 로 summary/content_markdown/deadline 을 얻는다.

        어떤 경우에도 예외를 밖으로 던지지 않는다(키 없음/실패 시 오프라인 폴백:
        요약=본문 앞부분, markdown=원문, deadline=None).
        """

        original = content or ""
        if not self.enabled:
            return self._enrich_fallback(original, note="LLM_API_KEY 미설정")

        truncated = original[:ENRICH_MAX_CONTENT_CHARS]
        try:
            data = self._chat_json(
                build_enrichment_messages(title=title, content=truncated)
            )
            return self._parse_enrichment(data, original)
        except Exception as exc:  # 결코 밖으로 던지지 않는다
            logger.warning(
                "LLM 보강 호출/파싱 실패 → 오프라인 폴백 전환 (model=%s): %s",
                self.model,
                exc,
            )
            return self._enrich_fallback(original, note="LLM 보강 실패")

    def _parse_enrichment(
        self, data: dict[str, Any], original_content: str
    ) -> Enrichment:
        summary = str(data.get("summary") or "").strip()
        markdown = str(data.get("content_markdown") or "").strip()

        deadline = data.get("deadline_at")
        if deadline is not None:
            deadline = str(deadline).strip() or None

        # 모델이 비워 보낸 필드는 원문 기반으로 보완해 정보 손실을 막는다.
        if not summary:
            summary = first_sentences(original_content, 3)
        if not markdown:
            markdown = (original_content or "").strip()

        return Enrichment(
            summary=summary,
            content_markdown=markdown,
            deadline=deadline,
            provider=PROVIDER_LLM,
        )

    def _enrich_fallback(self, content: str, *, note: str = "") -> Enrichment:
        """키 없음/호출 실패 시의 결정론적 보강(원문 보존).

        요약은 본문 앞 3문장, markdown 은 원문 그대로, 마감일은 알 수 없어 None.
        """

        if note:
            logger.debug("enrich fallback note: %s", note)
        text = (content or "").strip()
        return Enrichment(
            summary=first_sentences(text, 3),
            content_markdown=text,
            deadline=None,
            provider=PROVIDER_FALLBACK,
        )

    def _parse_verdict(self, data: dict[str, Any]) -> Verdict:
        score = data.get("score", 0.0)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))

        raw_keywords = data.get("matched_keywords") or []
        if isinstance(raw_keywords, str):
            keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        elif isinstance(raw_keywords, list):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            keywords = []

        relevant = bool(data.get("relevant", score > 0))
        reason = str(data.get("reason", "")).strip()
        return Verdict(
            relevant=relevant,
            score=score,
            matched_keywords=keywords,
            reason=reason,
            provider=PROVIDER_LLM,
        )

    def _fallback(
        self,
        title: str,
        content: str,
        interests: list[dict[str, Any]],
        *,
        note: str = "",
    ) -> Verdict:
        """키 없음/호출 실패 시의 결정론적 키워드 매칭.

        제목+본문에 대해 관심 키워드를 대소문자 무시 부분일치로 찾고, 매칭 개수
        비율로 점수를 낸다. 하나라도 매칭되면 기본 임계값(0.5)을 넘도록 설계했다.
        """

        haystack = f"{title or ''}\n{content or ''}".lower()
        keyworded = [
            (interest.get("keyword") or "").strip()
            for interest in interests
            if (interest.get("keyword") or "").strip()
        ]
        matched: list[str] = []
        for keyword in keyworded:
            if keyword.lower() in haystack and keyword not in matched:
                matched.append(keyword)

        if matched:
            fraction = len(matched) / max(len(keyworded), 1)
            score = round(min(1.0, 0.5 + 0.5 * fraction), 3)
            reason = "관심 키워드와 일치: " + ", ".join(matched)
        else:
            score = 0.0
            reason = "관심 키워드와 일치하는 내용 없음"
        # note(예: 'LLM 호출 실패')는 내부 디버깅용 — 사용자에게 보이는 reason 에는 넣지 않는다.
        if note:
            logger.debug("fallback reason note: %s", note)

        return Verdict(
            relevant=bool(matched),
            score=score,
            matched_keywords=matched,
            reason=reason,
            provider=PROVIDER_FALLBACK,
        )


def get_client() -> LLMClient:
    """settings 기반 기본 클라이언트 팩토리."""
    return LLMClient()
