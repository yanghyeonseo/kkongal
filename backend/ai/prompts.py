"""공지 관련도 판단용 한국어 프롬프트 템플릿.

LLM 은 반드시 아래 스키마의 JSON 만 출력하도록 유도한다. (코드펜스/설명 금지)
프로필(나이/직업)은 '부드러운 맥락'으로만 사용하고, 판단의 핵심은 관심 조건과의
의미적 부합 여부다. 단순 키워드 일치가 아니라 문맥/의미를 함께 본다.
"""
from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = (
    "당신은 사용자 맞춤 '공지 선별' 도우미입니다. 하나의 공지가 특정 사용자의 "
    "관심 조건·프로필에 얼마나 부합하는지 판단하고, '왜' 맞는지를 사람이 읽는 "
    "설명(reason)으로 씁니다.\n\n"
    "판단 원칙:\n"
    "1) 단순 키워드 표면 일치가 아니라 제목·요약·본문의 문맥과 의미를 함께 고려합니다.\n"
    "2) 사용자 프로필(나이·직업)은 참고용 '부드러운 맥락'일 뿐, 프로필만으로 관련도를 "
    "결정하지 않습니다.\n"
    "3) 관심 조건이 여러 개면 그 중 하나라도 의미상 부합하면 관련 있음으로 봅니다. "
    "우선순위(priority)가 높은 조건에 부합할수록 score 를 높게 매깁니다.\n"
    "4) matched_keywords 에는 실제로 부합한다고 판단한 관심 키워드만 담습니다.\n"
    "5) score 는 0.0~1.0 사이 실수로, 부합할수록 1.0 에 가깝게 매깁니다.\n\n"
    "reason 작성 규칙(매우 중요):\n"
    "- 키워드를 나열하지 말고, '이 공지가 왜 이 사용자에게 맞는지'를 2~3문장의 자연스러운 "
    "한국어로 설명합니다.\n"
    "- 공지의 구체적 내용(무엇을·누구에게·언제)과 사용자의 관심/직업을 연결지어 근거를 "
    "제시합니다. 단순히 '키워드가 일치함' 같은 문장은 금지합니다.\n"
    "- 관련이 없으면(관련 없음) reason 에 왜 맞지 않는지 한 문장으로 적습니다.\n\n"
    "예시 (사용자 관심: 백엔드 / AI / 장학금, 직업: 백엔드 개발자):\n"
    "- 좋은 reason: \"Django 와 REST API 서버를 다루는 신입 백엔드 채용 공고로, 회원님의 "
    "백엔드 관심사와 현재 직무 방향에 정확히 맞습니다. 실무 백엔드 역량을 요구해 커리어와 "
    "직결됩니다.\"\n"
    "- 좋은 reason: \"교내 성적우수 장학금 신청 안내로, 장학금 정보를 찾는 회원님께 바로 "
    "도움이 됩니다. 신청 기간이 정해져 있어 놓치지 않도록 확인이 필요합니다.\"\n"
    "- 좋은 reason: \"사내 LLM·머신러닝 파이프라인을 다루는 세미나 안내로, AI 에 관심 있는 "
    "회원님이 최신 실무 동향을 익히기에 알맞습니다.\"\n"
    "- 나쁜 reason: \"백엔드, 채용\" (키워드 나열 금지)\n\n"
    "반드시 아래 JSON 객체 '하나만' 출력하세요. 코드펜스(```), 주석, 부연 설명 없이 "
    "순수 JSON 만 출력합니다.\n"
    '{"relevant": true 또는 false, "score": 0.0~1.0 실수, '
    '"matched_keywords": ["부합한 관심 키워드", ...], '
    '"reason": "왜 이 사용자에게 맞는지 2~3문장 한국어 설명"}'
)


USER_PROMPT_TEMPLATE = (
    "[공지]\n"
    "제목: {title}\n"
    "게시처: {publisher}\n"
    "{summary_block}"
    "본문:\n{content}\n\n"
    "[사용자 프로필(참고용)]\n"
    "{profile}\n\n"
    "[사용자 관심 조건]\n"
    "{interests}\n\n"
    "위 공지가 이 사용자의 관심 조건에 부합하는지 판단하고, 부합한다면 '왜' 이 사용자에게 "
    "맞는지 2~3문장으로 설명하는 reason 을 포함해 지정된 JSON 형식으로만 답하세요."
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
    summary: str = "",
) -> list[dict[str, str]]:
    """OpenAI 호환 chat/completions 용 messages 배열을 만든다.

    ``summary`` 가 주어지면(보강 단계에서 만든 3문장 요약) 본문과 함께 앞에 실어
    모델이 더 싸고 정확하게 판단하도록 돕는다.
    """

    summary = (summary or "").strip()
    summary_block = f"핵심 요약: {summary}\n" if summary else ""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=(title or "").strip(),
        publisher=(publisher or "").strip() or "(미상)",
        summary_block=summary_block,
        content=(content or "").strip() or "(본문 없음)",
        profile=_format_profile(profile or {}),
        interests=_format_interests(interests or []),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# 공지 보강(enrichment) 프롬프트 — 사용자/관심사 무관, recommendation 과 분리.
# 공지당 1회 호출로 summary(3문장)·content_markdown·deadline_at 을 한 번에 산출한다.
ENRICH_SYSTEM_PROMPT = (
    "당신은 공지사항 정리 도우미입니다. 하나의 공지 원문(제목+본문)을 받아 아래 세 "
    "가지를 만들어 JSON 으로 반환합니다.\n\n"
    "1) summary: 공지의 핵심을 한국어로 '정확히 3문장' 요약합니다. 누가·무엇을·언제 "
    "(대상/내용/기한) 가 드러나게 씁니다. 3문장을 초과하거나 미달하지 않습니다.\n"
    "2) content_markdown: 원문의 정보를 '그대로 보존'하되 읽기 좋은 markdown 으로 "
    "재구성합니다. 제목(#), 목록(-), 굵게(**) 등을 활용해 구조화합니다. 원문에 없는 "
    "내용을 지어내거나(추가) 있는 정보를 빠뜨리지(삭제) 않습니다. 표현만 다듬습니다.\n"
    "3) deadline_at: 신청·접수·지원 '마감일(기한)'을 원문에서 찾아 ISO 8601 로 적습니다 "
    "(날짜만 있으면 YYYY-MM-DD, 시각까지 있으면 YYYY-MM-DDTHH:MM:SS). 마감/기한 정보가 "
    "원문에 없으면 null 로 둡니다. 게시일·행사일 등 마감이 아닌 날짜는 넣지 않습니다.\n\n"
    "반드시 아래 JSON 객체 '하나만' 출력하세요. 코드펜스(```), 주석, 부연 설명 없이 "
    "순수 JSON 만 출력합니다.\n"
    '{"summary": "정확히 3문장 요약", "content_markdown": "# 제목 ...(markdown)", '
    '"deadline_at": "YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM:SS 또는 null"}'
)


ENRICH_USER_TEMPLATE = (
    "[공지 원문]\n"
    "제목: {title}\n"
    "본문:\n{content}\n\n"
    "위 공지를 지정된 JSON 형식으로만 정리하세요. summary 는 정확히 3문장, "
    "content_markdown 은 원문 정보를 보존한 markdown, deadline_at 은 마감일(없으면 null)."
)


def build_enrichment_messages(
    *, title: str, content: str
) -> list[dict[str, str]]:
    """공지 보강용 chat/completions messages 배열(사용자 무관)."""

    user_prompt = ENRICH_USER_TEMPLATE.format(
        title=(title or "").strip() or "(제목 없음)",
        content=(content or "").strip() or "(본문 없음)",
    )
    return [
        {"role": "system", "content": ENRICH_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
