"""공지 관련도 판단용 한국어 프롬프트 템플릿.

꽁알꽁알은 채용·장학뿐 아니라 콘서트 티켓 선예매, 커뮤니티 글, 스타트업 지원사업 등
'모든 종류의 공지'를 다루는 도메인 중립 서비스다. LLM 은 반드시 아래 스키마의 JSON 만
출력하도록 유도한다(코드펜스/설명 금지). 프로필은 두 층으로 나뉜다: 고정 필드
(나이·성별·지역·직업)와 자유서술 bio, 그리고 사용자가 직접 추가한 '추가 정보'
(배경·자격: 지역 거주, 국가유공자, 팬클럽 가입, 직급/부서 등). 이 정보들은 '부드러운
맥락'인 동시에, 공지의 대상/자격요건과 부합하면 관련도를 높이고 충돌하면 낮추는 근거가
될 수 있다. 판단의 핵심은 관심 조건과의 의미적 부합 여부이며, 단순 키워드 일치가 아니라
문맥/의미를 함께 본다.
"""
from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = (
    "당신은 사용자 맞춤 '공지 선별' 도우미입니다. 하나의 공지가 특정 사용자의 "
    "관심 조건·프로필에 얼마나 부합하는지 판단하고, '왜' 맞는지를 사람이 읽는 "
    "설명(reason)으로 씁니다. 공지는 채용·장학뿐 아니라 콘서트 티켓 선예매, 커뮤니티 "
    "모임, 스타트업 지원사업 등 무엇이든 될 수 있으므로 특정 도메인을 전제하지 마세요.\n\n"
    "판단 원칙:\n"
    "1) 단순 키워드 표면 일치가 아니라 제목·요약·본문의 문맥과 의미를 함께 고려합니다.\n"
    "2) 사용자 프로필은 고정 필드(나이·성별·지역·직업)와 자유서술 bio, 그리고 사용자가 "
    "직접 추가한 '추가 정보(배경·자격)'로 이뤄집니다. 추가 정보에는 도메인에 따라 지역 "
    "거주, 국가유공자 여부, 가입 팬클럽, 직급/부서, 학교/전공 등 무엇이든 담길 수 있습니다. "
    "이 프로필은 참고용 '부드러운 맥락'인 동시에, 공지의 '대상·자격요건'과 부합하면 관련도를 "
    "높이고 충돌하면(예: 특정 지역·자격·소속 조건 미충족) 낮추는 '하드 제약'의 근거가 될 수 "
    "있습니다. 다만 프로필만으로 관련도를 결정하지는 않습니다(관심 조건과의 의미적 부합이 "
    "핵심).\n"
    "3) 관심 조건이 여러 개면 그 중 하나라도 의미상 부합하면 관련 있음으로 봅니다. "
    "우선순위(priority)가 높은 조건에 부합할수록 score 를 높게 매깁니다.\n"
    "4) matched_keywords 에는 실제로 부합한다고 판단한 관심 키워드만 담습니다.\n"
    "5) score 는 0.0~1.0 사이 실수로, 부합할수록 1.0 에 가깝게 매깁니다.\n\n"
    "reason 작성 규칙(매우 중요):\n"
    "- 키워드를 나열하지 말고, '이 공지가 왜 이 사용자에게 맞는지'를 2~3문장의 자연스러운 "
    "한국어로 설명합니다.\n"
    "- 공지의 구체적 내용(무엇을·누구에게·언제)과 사용자의 관심/프로필을 연결지어 근거를 "
    "제시합니다. 단순히 '키워드가 일치함' 같은 문장은 금지합니다.\n"
    "- 관련이 없으면(관련 없음) reason 에 왜 맞지 않는지 한 문장으로 적습니다.\n\n"
    "예시 (다양한 도메인):\n"
    "- 좋은 reason: \"Django 와 REST API 서버를 다루는 신입 백엔드 채용 공고로, 회원님의 "
    "백엔드 관심사와 현재 직무 방향에 정확히 맞습니다. 실무 백엔드 역량을 요구해 커리어와 "
    "직결됩니다.\"\n"
    "- 좋은 reason: \"가입 팬클럽 회원을 대상으로 한 콘서트 티켓 선예매 안내로, 해당 팬클럽에 "
    "가입한 회원님께 예매 우선권이 주어집니다. 선예매 기간이 짧으니 서둘러 확인이 "
    "필요합니다.\"\n"
    "- 좋은 reason: \"초기 창업팀을 위한 정부 지원사업 모집 공고로, 스타트업을 준비하는 "
    "회원님이 자금과 멘토링을 받을 수 있는 기회입니다. 접수 마감이 정해져 있어 일정 확인이 "
    "필요합니다.\"\n"
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


# (profile 키, 한국어 라벨) — 고정(보편) 필드는 이 순서대로 한 줄씩 렌더한다.
# bio(자유서술)와 사용자 지정 추가 정보(attributes)는 별도 블록으로 렌더한다.
_PROFILE_LABELS: list[tuple[str, str]] = [
    ("age", "나이"),
    ("gender", "성별"),
    ("region", "지역"),
    ("job", "직업"),
]


def _format_profile(profile: dict[str, Any]) -> str:
    """사용자 프로필을 라벨이 붙은 여러 줄 문자열로 렌더한다.

    고정 필드(나이/성별/지역/직업)는 값이 있는 것만 한 줄씩 담고, 자유서술(bio)은
    '기타(자유 서술)' 블록으로 따로 붙인다. 사용자가 직접 추가한 커스텀 필드
    (``profile["attributes"]`` = ``[{"label":..., "value":...}, ...]``)는
    '추가 정보(사용자 지정)' 섹션에 ``- label: value`` 로 나열한다. 비어 있거나
    None 인 값·빈 리스트는 건너뛴다. 아무 정보도 없으면 '(프로필 정보 없음)'.
    """

    lines: list[str] = []
    for key, label in _PROFILE_LABELS:
        value = profile.get(key)
        # age 는 정수라 0(실질적으로 '없음')은 건너뛴다. 나머지는 문자열 → 공백 제거 후 판정.
        if key == "age" and not value:
            continue
        text = str(value).strip() if value is not None else ""
        if text:
            lines.append(f"- {label}: {text}")

    bio = (profile.get("bio") or "").strip()
    if bio:
        lines.append(f"- 기타(자유 서술): {bio}")

    # 사용자 지정 추가 정보(도메인별 배경·자격) — label/value 쌍을 섹션으로 렌더.
    attribute_lines: list[str] = []
    for attribute in profile.get("attributes") or []:
        label = str(attribute.get("label") or "").strip()
        value = str(attribute.get("value") or "").strip()
        if label and value:
            attribute_lines.append(f"- {label}: {value}")
    if attribute_lines:
        lines.append("추가 정보(사용자 지정):")
        lines.extend(attribute_lines)

    return "\n".join(lines) or "(프로필 정보 없음)"


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
