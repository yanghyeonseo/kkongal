"""AI 기반 사이트 이름·카테고리 자동 채우기 — NoticeSource 당 1회만 수행한다.

새 소스가 등록되면 이름은 도메인에서 기계적으로 만든 값(``naming.friendly_name_for``),
카테고리는 기본값 "etc" 로 시작한다. 이 모듈은 최근 공지 제목 샘플과 사이트 URL/현재
이름을 LLM 에 보여줘 더 자연스러운 한국어 이름과 카테고리를 추론해 채운다.

- 이미 ``ai_named`` 인 소스는 다시 호출하지 않는다(비용 방어, 매 동기화마다 재호출 금지).
- LLM 이 비활성(키 없음)이거나 결과가 비어 있으면 아무 것도 바꾸지 않고 조용히 리턴한다
  (``ai_named`` 를 세우지 않아 LLM 이 살아나면 다음 동기화에서 다시 시도한다).
- 사용자가 이미 손으로 고친 이름/카테고리는 절대 덮어쓰지 않는다.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ai.llm import get_client

from .models import NoticeSource
from .naming import friendly_name_for

log = logging.getLogger("sources.ai_naming")

# 카테고리로 우선 고려할 알려진 슬러그 집합. 이 중 하나가 맞으면 그대로 쓰고, 없으면
# LLM 이 새로운 짧은 영문 소문자 슬러그를 제안할 수 있다(예: "startup").
KNOWN_CATEGORIES = (
    "school",
    "job",
    "scholarship",
    "activity",
    "contest",
    "community",
    "culture",
    "etc",
)

_MAX_TITLES = 10
_CATEGORY_MAX_LEN = 32
_NAME_MAX_LEN = 128

_SYSTEM_PROMPT = (
    "당신은 웹사이트/게시판의 사람이 읽는 한국어 이름과 카테고리를 추론하는 도우미입니다. "
    "주어진 사이트 URL, 현재 이름, 최근 게시글 제목 샘플을 보고 이 사이트를 가장 잘 "
    "나타내는 짧은 한국어 이름과 카테고리를 판단합니다.\n\n"
    "규칙:\n"
    f"1) category 는 가능하면 다음 목록 중 하나를 그대로 씁니다: {', '.join(KNOWN_CATEGORIES)}.\n"
    "2) 목록에 맞는 카테고리가 없으면 새로운 짧은 영문 소문자 슬러그(예: 'startup')를 "
    "만들어도 됩니다. 공백 없이 알파벳(및 밑줄)만 사용합니다.\n"
    "3) name 은 사람이 읽기 좋은 짧은 한국어 사이트 이름입니다(예: '더드림코리아'). "
    "도메인을 그대로 베끼지 말고, 제목 샘플에서 드러나는 주체/기관명을 우선 반영합니다.\n\n"
    "반드시 아래 JSON 객체 하나만 출력하세요. 코드펜스, 설명, 주석 없이 순수 JSON 만 "
    "출력합니다.\n"
    '{"name": "짧은 한국어 사이트 이름", "category": "카테고리 슬러그"}'
)

_USER_PROMPT_TEMPLATE = (
    "[사이트 URL]\n{url}\n\n"
    "[현재 이름]\n{name}\n\n"
    "[최근 게시글 제목 샘플]\n{titles}\n\n"
    "위 정보를 바탕으로 이 사이트의 이름과 카테고리를 지정된 JSON 형식으로만 답하세요."
)


def _build_messages(*, url: str, name: str, titles: list[str]) -> list[dict[str, str]]:
    titles_block = "\n".join(f"- {t}" for t in titles) if titles else "(샘플 없음)"
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        url=url, name=name or "(없음)", titles=titles_block
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _sanitize_category(raw: Any) -> str:
    """카테고리 문자열을 소문자 [a-z_] 로만 정제한다. 비면 "etc"."""
    text = str(raw or "").strip().lower()
    cleaned = re.sub(r"[^a-z_]", "", text)
    cleaned = cleaned[:_CATEGORY_MAX_LEN]
    return cleaned or "etc"


def _sanitize_name(raw: Any) -> str:
    return str(raw or "").strip()[:_NAME_MAX_LEN]


def autofill_source_metadata(source: NoticeSource) -> None:
    """source.name/category 를 LLM 추론으로 채운다(성공 시 1회만).

    실패해도(비활성/빈 결과/예외) 절대 예외를 밖으로 던지지 않는다 — 크롤/동기화
    파이프라인을 절대 깨뜨리면 안 된다.
    """
    try:
        _autofill_source_metadata(source)
    except Exception:  # noqa: BLE001 - 메타데이터 보강 실패가 상위 파이프라인을 깨면 안 된다.
        log.exception("autofill_source_metadata 실패(source_id=%s)", getattr(source, "id", None))


def _autofill_source_metadata(source: NoticeSource) -> None:
    if source.ai_named:
        return

    from notices.models import Notice

    titles = list(
        Notice.objects.filter(source_id=source)
        .order_by("-id")
        .values_list("title", flat=True)[:_MAX_TITLES]
    )
    titles = [t for t in titles if t]

    client = get_client()
    if not client.enabled:
        log.debug("LLM 비활성 → autofill 보류(source_id=%s)", source.id)
        return

    messages = _build_messages(url=source.url, name=source.name, titles=titles)
    data = client.complete_json(messages)
    if not data:
        log.debug("LLM 결과 비어 있음 → autofill 보류(source_id=%s)", source.id)
        return

    raw_name = data.get("name")
    raw_category = data.get("category")
    if not raw_name and not raw_category:
        log.debug("LLM 결과 사용 불가 → autofill 보류(source_id=%s)", source.id)
        return

    update_fields: list[str] = []

    # 카테고리: 비어있거나 아직 미분류("etc")일 때만 덮어쓴다(사용자가 정한 값 보존).
    if source.category in ("", "etc"):
        category = _sanitize_category(raw_category)
        if category and category != source.category:
            source.category = category
            update_fields.append("category")

    # 이름: 비어있거나 도메인에서 기계적으로 만든 값 그대로일 때만 덮어쓴다.
    auto_name = friendly_name_for(source.url)
    if not source.name or source.name == auto_name:
        name = _sanitize_name(raw_name)
        if name and name != source.name:
            source.name = name
            update_fields.append("name")

    source.ai_named = True
    update_fields.append("ai_named")

    source.save(update_fields=update_fields)
