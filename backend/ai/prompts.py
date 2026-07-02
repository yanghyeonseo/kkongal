"""공지 관련도 판단용 한국어 프롬프트 템플릿.

LLM 은 반드시 아래 스키마의 JSON 만 출력하도록 유도한다. (코드펜스/설명 금지)
프로필(나이/직업)은 '부드러운 맥락'으로만 사용하고, 판단의 핵심은 관심 조건과의
의미적 부합 여부다. 단순 키워드 일치가 아니라 문맥/의미를 함께 본다.
"""
from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = (
    "당신은 사용자 맞춤 '공지 선별' 도우미입니다. 하나의 공지가 특정 사용자의 "
    "관심 조건에 부합하는지 판단하세요.\n"
    "판단 원칙:\n"
    "1) 단순 키워드 일치가 아니라 제목·본문의 문맥과 의미를 함께 고려합니다.\n"
    "2) 사용자 프로필(나이·직업)은 참고용 '부드러운 맥락'일 뿐, 프로필만으로 관련도를 "
    "결정하지 않습니다.\n"
    "3) 관심 조건이 여러 개면 그 중 하나라도 의미상 부합하면 관련 있음으로 봅니다. "
    "우선순위(priority)가 높은 조건에 부합할수록 관련도를 높게 매깁니다.\n"
    "4) matched_keywords 에는 실제로 관련되었다고 판단한 관심 키워드만 담습니다.\n"
    "5) score 는 0.0~1.0 사이 실수로, 부합할수록 1.0 에 가깝게 매깁니다.\n\n"
    "반드시 아래 JSON 객체 '하나만' 출력하세요. 코드펜스(```), 주석, 부연 설명 없이 "
    "순수 JSON 만 출력합니다.\n"
    '{"relevant": true 또는 false, "score": 0.0~1.0 실수, '
    '"matched_keywords": ["관련 키워드", ...], "reason": "간단한 한국어 사유"}'
)


USER_PROMPT_TEMPLATE = (
    "[공지]\n"
    "제목: {title}\n"
    "게시처: {publisher}\n"
    "본문:\n{content}\n\n"
    "[사용자 프로필(참고용)]\n"
    "{profile}\n\n"
    "[사용자 관심 조건]\n"
    "{interests}\n\n"
    "위 공지가 이 사용자의 관심 조건에 부합하는지 판단하여 지정된 JSON 형식으로만 "
    "답하세요."
)


def _format_interests(interests: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, interest in enumerate(interests, start=1):
        keyword = (interest.get("keyword") or "").strip()
        description = (interest.get("description") or "").strip()
        priority = interest.get("priority", 0)
        parts: list[str] = []
        if keyword:
            parts.append(f"키워드='{keyword}'")
        if description:
            parts.append(f"설명='{description}'")
        parts.append(f"우선순위={priority}")
        lines.append(f"{idx}. " + ", ".join(parts))
    return "\n".join(lines) or "(등록된 관심 조건 없음)"


def _format_profile(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    age = profile.get("age")
    job = (profile.get("job") or "").strip()
    if age:
        parts.append(f"나이={age}")
    if job:
        parts.append(f"직업='{job}'")
    return ", ".join(parts) or "(프로필 정보 없음)"


def build_messages(
    *,
    title: str,
    content: str,
    publisher: str,
    profile: dict[str, Any],
    interests: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """OpenAI 호환 chat/completions 용 messages 배열을 만든다."""

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=(title or "").strip(),
        publisher=(publisher or "").strip() or "(미상)",
        content=(content or "").strip() or "(본문 없음)",
        profile=_format_profile(profile or {}),
        interests=_format_interests(interests or []),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
