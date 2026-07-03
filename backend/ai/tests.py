"""ai 앱 테스트.

네트워크 없이 두 경로를 모두 검증한다:
- 폴백 경로: LLM_API_KEY 미설정 → 키워드 매칭.
- LLM 경로: httpx.MockTransport 로 chat/completions 응답을 가짜로 주입.
"""
from __future__ import annotations

import json
from io import StringIO

import httpx
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from account.models import Interest
from notices.models import InboxNotice, Notice
from sources.models import NoticeSource, SourceSubscription

from ai.enrich import enrich_notice, enrich_notices, parse_deadline
from ai.llm import PROVIDER_FALLBACK, PROVIDER_LLM, LLMClient, extract_json
from ai.prompts import build_messages
from ai.service import NAIVE_REASON, classify_notice, run_classification

User = get_user_model()


def _completion(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
            ]
        },
    )


def make_fixed_client(content: str, *, status_code: int = 200) -> LLMClient:
    """입력과 무관하게 항상 같은 content 문자열을 반환하는 LLM 클라이언트."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"choices": [{"message": {"content": content}}]},
        )

    return LLMClient(api_key="test-key", transport=httpx.MockTransport(handler))


def make_smart_client() -> LLMClient:
    """관심 키워드가 '채용' 인 사용자에게만 높은 점수를 주는 클라이언트."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_msg = body["messages"][-1]["content"]
        if "키워드='채용'" in user_msg:
            return _completion(
                {
                    "relevant": True,
                    "score": 0.9,
                    "matched_keywords": ["채용"],
                    "reason": "채용 공고로 판단",
                }
            )
        return _completion(
            {
                "relevant": False,
                "score": 0.1,
                "matched_keywords": [],
                "reason": "관련 없음",
            }
        )

    return LLMClient(api_key="test-key", transport=httpx.MockTransport(handler))


def make_capturing_client(payload: dict):
    """항상 ``payload`` 를 반환하되, 마지막 요청의 messages 를 기록하는 클라이언트.

    recommendation 입력에 summary 가 실렸는지 등 프롬프트 구성 검증에 쓴다.
    """

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["system"] = body["messages"][0]["content"]
        captured["user"] = body["messages"][-1]["content"]
        return _completion(payload)

    client = LLMClient(api_key="test-key", transport=httpx.MockTransport(handler))
    return client, captured


class BaseFixtures(TestCase):
    def setUp(self) -> None:
        self.source = NoticeSource.objects.create(
            name="테스트 공지처", url="https://example.com/notices"
        )
        self.user_match = User.objects.create_user(
            username="matcher",
            email="matcher@example.com",
            age=26,
            job="백엔드 개발자",
        )
        self.user_nomatch = User.objects.create_user(
            username="nomatcher",
            email="nomatcher@example.com",
            age=30,
            job="디자이너",
        )
        Interest.objects.create(
            user_id=self.user_match,
            keyword="채용",
            description="신입 백엔드 채용 공고",
            priority=5,
        )
        Interest.objects.create(
            user_id=self.user_nomatch,
            keyword="장학금",
            description="교내 장학금 안내",
            priority=3,
        )
        SourceSubscription.objects.create(
            user_id=self.user_match, source_id=self.source
        )
        SourceSubscription.objects.create(
            user_id=self.user_nomatch, source_id=self.source
        )
        self.notice = Notice.objects.create(
            source_id=self.source,
            url="https://example.com/notices/1",
            title="2026 신입 백엔드 개발자 채용 공고",
            content="ACME 에서 백엔드 개발자를 채용합니다. 지원 바랍니다.",
            publisher="ACME",
        )


@override_settings(LLM_API_KEY="", LLM_RELEVANCE_THRESHOLD=0.5)
class FallbackPathTests(BaseFixtures):
    def test_fallback_creates_for_match_and_skips_nonmatch(self) -> None:
        summary = run_classification()

        self.assertEqual(summary.provider, PROVIDER_FALLBACK)
        self.assertEqual(summary.notices_processed, 1)
        # 매칭 사용자는 inbox 생성 + 추천(is_recommended=True)
        self.assertTrue(
            InboxNotice.objects.filter(
                user_id=self.user_match, notice_id=self.notice
            ).exists()
        )
        # store-all: 비매칭 사용자도 저장하되 비추천(is_recommended=False)으로 남긴다.
        nomatch_row = InboxNotice.objects.get(
            user_id=self.user_nomatch, notice_id=self.notice
        )
        self.assertFalse(nomatch_row.is_recommended)
        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertTrue(row.is_recommended)
        self.assertGreaterEqual(row.relevance_score, 0.5)
        self.assertIn("채용", row.matched_keywords)
        self.assertIn("관심 키워드·설명과 일치", row.reason)
        # 내부 note(미설정/실패 등)는 사용자 노출 reason 에 새지 않아야 한다.
        self.assertNotIn("미설정", row.reason)
        self.assertNotIn("실패", row.reason)

    def test_api_failure_falls_back(self) -> None:
        # 키는 있지만 API 가 500 → 폴백으로 전환(예외 전파 없음)
        client = make_fixed_client("irrelevant", status_code=500)
        summary = run_classification(client=client, threshold=0.5)

        self.assertEqual(summary.provider, PROVIDER_FALLBACK)
        self.assertTrue(
            InboxNotice.objects.filter(user_id=self.user_match).exists()
        )

    def test_skips_already_classified(self) -> None:
        # store-all: 매칭 사용자(추천)와 비매칭 사용자(비추천) 둘 다 행이 생성된다.
        first = classify_notice(self.notice)
        self.assertEqual(first.created, 2)

        second = classify_notice(self.notice)  # reclassify=False → 기존 쌍 모두 생략
        self.assertEqual(second.skipped_existing, 2)  # 두 사용자 모두 AI 행 존재 → 생략
        self.assertEqual(second.candidates, 0)  # 재평가 대상 없음
        self.assertEqual(
            InboxNotice.objects.filter(notice_id=self.notice).count(), 2
        )

    def test_run_classification_default_excludes_only_real_ai_notice(self) -> None:
        # 폴백도 'AI 계층'의 출력이므로 그 행은 진짜 분류로 취급된다(순진한 매처와 구분).
        run_classification()  # user_match 에 진짜-AI 행 생성
        # 두 번째 기본 실행은 진짜-AI 분류가 끝난 공지를 후보에서 제외 → 처리 0
        summary = run_classification()
        self.assertEqual(summary.notices_processed, 0)


class LLMPathTests(BaseFixtures):
    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_llm_path_creates_for_relevant_only(self) -> None:
        client = make_smart_client()
        summary = run_classification(client=client)

        self.assertEqual(summary.provider, PROVIDER_LLM)
        self.assertEqual(summary.llm_calls, 2)
        # store-all: 두 사용자 모두 행 생성. 매칭만 추천, 비매칭은 비추천.
        self.assertEqual(summary.created, 2)
        self.assertEqual(summary.recommended, 1)
        self.assertEqual(summary.below_threshold, 1)

        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertAlmostEqual(row.relevance_score, 0.9)
        self.assertEqual(row.reason, "채용 공고로 판단")
        self.assertEqual(row.matched_keywords, "채용")
        self.assertTrue(row.is_recommended)
        # 비매칭 사용자도 저장되지만 is_recommended=False (전체 공지엔 보이고 추천/알림엔 제외).
        nomatch_row = InboxNotice.objects.get(user_id=self.user_nomatch)
        self.assertFalse(nomatch_row.is_recommended)

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_idempotent_update_or_create(self) -> None:
        client = make_smart_client()
        run_classification(client=client)
        # reclassify=True 로 같은 쌍 재판정 → 갱신(중복 생성 아님).
        # store-all: 매칭·비매칭 두 쌍 모두 기존 행을 갱신한다.
        summary = run_classification(client=client, reclassify=True)

        self.assertEqual(summary.updated, 2)
        self.assertEqual(summary.created, 0)
        self.assertEqual(
            InboxNotice.objects.filter(
                user_id=self.user_match, notice_id=self.notice
            ).count(),
            1,
        )

    def test_threshold_gating_marks_low_score_not_recommended(self) -> None:
        # store-all: 임계값 미만 판정도 삭제하지 않고 is_recommended=False 로 저장한다.
        content = json.dumps(
            {
                "relevant": True,
                "score": 0.5,
                "matched_keywords": ["채용"],
                "reason": "약한 관련",
            }
        )
        client = make_fixed_client(content)
        summary = run_classification(client=client, threshold=0.8)

        self.assertEqual(summary.created, 2)
        self.assertEqual(summary.recommended, 0)
        self.assertEqual(summary.below_threshold, 2)
        # 두 행 모두 저장되지만 어느 것도 추천이 아니다.
        self.assertEqual(InboxNotice.objects.count(), 2)
        self.assertFalse(
            InboxNotice.objects.filter(is_recommended=True).exists()
        )

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_defensive_parsing_of_codefenced_response(self) -> None:
        payload = {
            "relevant": True,
            "score": 0.77,
            "matched_keywords": ["채용"],
            "reason": "코드펜스 응답",
        }
        content = "다음이 결과입니다:\n```json\n" + json.dumps(
            payload, ensure_ascii=False
        ) + "\n```\n감사합니다."
        client = make_fixed_client(content)
        run_classification(client=client, threshold=0.5)

        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertAlmostEqual(row.relevance_score, 0.77)
        self.assertEqual(row.reason, "코드펜스 응답")

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_score_above_one_clamped_to_one(self) -> None:
        content = json.dumps(
            {
                "relevant": True,
                "score": 4.2,  # 범위 밖(상한 초과)
                "matched_keywords": "채용, 백엔드",  # 문자열 형태도 허용
                "reason": "과도한 점수",
            }
        )
        client = make_fixed_client(content)
        run_classification(client=client, threshold=0.5)

        row = InboxNotice.objects.get(user_id=self.user_match)
        # 상한 클램프는 정확히 1.0 이어야 한다.
        self.assertEqual(row.relevance_score, 1.0)
        self.assertEqual(row.matched_keywords, "채용, 백엔드")

    def test_score_below_zero_clamped_to_zero(self) -> None:
        client = make_fixed_client(
            json.dumps(
                {
                    "relevant": True,
                    "score": -1.0,  # 범위 밖(하한 미만)
                    "matched_keywords": ["채용"],
                    "reason": "음수 점수",
                }
            )
        )
        verdict = client.classify(
            title="제목", content="본문", interests=[{"keyword": "채용"}]
        )
        self.assertEqual(verdict.score, 0.0)


class AiAuthoritativeTests(BaseFixtures):
    """AI 가 순진한 매처(crawler/matcher.py)의 플레이스홀더를 덮어쓰는지 검증."""

    def _make_naive_row(self, user) -> InboxNotice:
        # crawler/matcher.py 가 크롤링 시점에 남기는 순진한 행을 재현(score 1.0).
        return InboxNotice.objects.create(
            user_id=user,
            notice_id=self.notice,
            relevance_score=1.0,
            matched_keywords="채용",
            reason=NAIVE_REASON,
        )

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_ai_overrides_naive_keyword_match_row(self) -> None:
        naive = self._make_naive_row(self.user_match)

        summary = run_classification(client=make_smart_client())

        # 순진한 행이 있어도 공지는 후보에서 제외되지 않고 처리된다.
        self.assertEqual(summary.notices_processed, 1)
        # 순진한 행은 생략(skip)이 아니라 덮어쓰기(update) 대상.
        self.assertEqual(summary.skipped_existing, 0)
        self.assertEqual(summary.updated, 1)
        # store-all: 비매칭 사용자(user_nomatch)의 비추천 행이 새로 생성된다.
        self.assertEqual(summary.created, 1)

        row = InboxNotice.objects.get(id=naive.id)  # 같은 행이 갱신됨(중복 아님)
        self.assertAlmostEqual(row.relevance_score, 0.9)  # 1.0 → 0.9 로 override
        self.assertEqual(row.reason, "채용 공고로 판단")
        self.assertEqual(row.matched_keywords, "채용")
        self.assertTrue(row.is_recommended)  # 덮어쓴 행은 추천으로 판정됨
        self.assertEqual(
            InboxNotice.objects.filter(notice_id=self.notice).count(), 2
        )

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_real_ai_row_is_skipped_not_overwritten(self) -> None:
        # 진짜-AI 행(사유가 'Keyword match' 아님)은 reclassify 없이는 생략된다.
        InboxNotice.objects.create(
            user_id=self.user_match,
            notice_id=self.notice,
            relevance_score=0.9,
            matched_keywords="채용",
            reason="채용 공고로 판단",
        )
        summary = classify_notice(self.notice, client=make_smart_client())
        self.assertEqual(summary.skipped_existing, 1)
        self.assertEqual(summary.updated, 0)

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_ai_override_below_threshold_marks_naive_not_recommended(self) -> None:
        # store-all: 순진한 매처 오탐(1.0) 행을 AI 가 '관련 없음'으로 덮어쓰되 삭제하지 않고
        # is_recommended=False 로 표시한다('전체 공지'엔 남고 추천/알림에선 빠진다).
        naive = self._make_naive_row(self.user_match)
        low_client = make_fixed_client(
            json.dumps(
                {
                    "relevant": False,
                    "score": 0.1,
                    "matched_keywords": [],
                    "reason": "실제로는 관련 없음",
                }
            )
        )
        summary = run_classification(client=low_client)

        # 순진한 행은 애초에 is_recommended=False 였으므로 '추천→비추천' 전환이 아니다.
        self.assertEqual(summary.downgraded, 0)
        row = InboxNotice.objects.get(id=naive.id)  # 같은 행이 살아있고 갱신됨
        self.assertFalse(row.is_recommended)
        self.assertAlmostEqual(row.relevance_score, 0.1)
        self.assertEqual(row.reason, "실제로는 관련 없음")

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_reclassify_below_threshold_marks_row_not_recommended(self) -> None:
        # 먼저 관련 있음으로 분류되어 추천 행이 생성됨.
        run_classification(client=make_smart_client(), threshold=0.5)
        self.assertTrue(
            InboxNotice.objects.filter(
                user_id=self.user_match,
                notice_id=self.notice,
                is_recommended=True,
            ).exists()
        )
        # 재판정에서 점수가 임계값 밑으로 → 행을 삭제하지 않고 is_recommended=False 로 전환.
        low_client = make_fixed_client(
            json.dumps(
                {
                    "relevant": False,
                    "score": 0.2,
                    "matched_keywords": [],
                    "reason": "이제 관련 없음",
                }
            )
        )
        summary = run_classification(
            client=low_client, threshold=0.5, reclassify=True
        )

        # 추천→비추천으로 뒤집힌 행이 downgraded 로 집계된다(삭제 아님).
        self.assertEqual(summary.downgraded, 1)
        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertFalse(row.is_recommended)
        self.assertAlmostEqual(row.relevance_score, 0.2)

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_classify_never_touches_notified_at(self) -> None:
        # 이미 알림 발송된(notified_at 설정) 진짜-AI 행을 준비.
        sent_at = timezone.now()
        InboxNotice.objects.create(
            user_id=self.user_match,
            notice_id=self.notice,
            relevance_score=0.6,
            matched_keywords="채용",
            reason="채용 공고로 판단",
            notified_at=sent_at,
        )
        # reclassify 로 점수/사유가 갱신되어도 notified_at 은 보존되어야 한다(불변).
        run_classification(
            client=make_smart_client(), threshold=0.5, reclassify=True
        )
        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertAlmostEqual(row.relevance_score, 0.9)  # 갱신은 일어남
        self.assertEqual(row.notified_at, sent_at)  # notified_at 은 불변


class ExtractJsonUnitTests(TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_json_code_fence(self) -> None:
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_bare_code_fence(self) -> None:
        self.assertEqual(extract_json('```\n{"a": 1}\n```'), {"a": 1})

    def test_surrounding_prose(self) -> None:
        self.assertEqual(extract_json('결과: {"a": 1} 끝.'), {"a": 1})

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            extract_json("   ")

    def test_no_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            extract_json("아무 JSON 도 없음")


class ManagementCommandTests(BaseFixtures):
    @override_settings(LLM_API_KEY="", LLM_RELEVANCE_THRESHOLD=0.5)
    def test_command_runs_with_fallback(self) -> None:
        out = StringIO()
        call_command("classify_notices", stdout=out)
        output = out.getvalue()

        self.assertIn("classify_notices 완료", output)
        self.assertIn("판정 경로: fallback", output)
        self.assertTrue(
            InboxNotice.objects.filter(user_id=self.user_match).exists()
        )

    @override_settings(LLM_API_KEY="", LLM_RELEVANCE_THRESHOLD=0.5)
    def test_dry_run_writes_nothing(self) -> None:
        out = StringIO()
        call_command("classify_notices", "--dry-run", stdout=out)

        self.assertIn("[dry-run]", out.getvalue())
        self.assertFalse(InboxNotice.objects.exists())

    def test_invalid_since_raises(self) -> None:
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("classify_notices", "--since", "not-a-date")


@override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
class EnrichmentTests(TestCase):
    """공지 보강(enrich_notice/enrich_notices) — LLM 목/오프라인 폴백 모두 검증."""

    def setUp(self) -> None:
        self.source = NoticeSource.objects.create(
            name="장학팀", url="https://example.com/scholarship"
        )
        self.notice = Notice.objects.create(
            source_id=self.source,
            url="https://example.com/scholarship/1",
            title="2026-1학기 성적우수 장학금 신청 안내",
            content=(
                "2026학년도 1학기 성적우수 장학금을 신청받습니다. "
                "지원 대상은 직전 학기 평점 4.0 이상 재학생입니다. "
                "신청 기간은 2026-03-15 까지이며 학생포털에서 접수합니다."
            ),
            publisher="학생지원팀",
        )

    def test_enrich_parses_json_and_saves_three_fields(self) -> None:
        payload = {
            "summary": (
                "성적우수 장학금을 신청받습니다. 대상은 평점 4.0 이상 재학생입니다. "
                "신청은 3월 15일까지입니다."
            ),
            "content_markdown": (
                "# 성적우수 장학금\n\n- **대상**: 평점 4.0 이상 재학생\n"
                "- **마감**: 2026-03-15"
            ),
            "deadline_at": "2026-03-15",
        }
        client = make_fixed_client(json.dumps(payload, ensure_ascii=False))
        result = enrich_notice(self.notice, client=client)

        self.assertEqual(result["status"], "enriched")
        self.assertEqual(result["provider"], PROVIDER_LLM)
        self.assertTrue(result["deadline_at"])

        self.notice.refresh_from_db()
        self.assertEqual(self.notice.summary, payload["summary"])
        self.assertEqual(
            self.notice.content_markdown, payload["content_markdown"]
        )
        self.assertIsNotNone(self.notice.deadline_at)
        self.assertEqual(
            (
                self.notice.deadline_at.year,
                self.notice.deadline_at.month,
                self.notice.deadline_at.day,
            ),
            (2026, 3, 15),
        )
        self.assertTrue(timezone.is_aware(self.notice.deadline_at))

    def test_enrich_idempotent_skip_when_already_summarized(self) -> None:
        self.notice.summary = "이미 요약된 공지입니다. 두 번째 문장. 세 번째 문장."
        self.notice.save(update_fields=["summary"])

        # 호출되면 summary 를 바꿔버릴 클라이언트지만, skip 이면 건드리지 않아야 한다.
        client = make_fixed_client(
            json.dumps(
                {"summary": "새 요약", "content_markdown": "x", "deadline_at": None},
                ensure_ascii=False,
            )
        )
        result = enrich_notice(self.notice, client=client)

        self.assertEqual(result["status"], "skipped")
        self.notice.refresh_from_db()
        self.assertEqual(
            self.notice.summary, "이미 요약된 공지입니다. 두 번째 문장. 세 번째 문장."
        )

    def test_enrich_force_reenriches_even_if_summarized(self) -> None:
        self.notice.summary = "옛 요약."
        self.notice.save(update_fields=["summary"])
        payload = {
            "summary": "새 요약 1. 새 요약 2. 새 요약 3.",
            "content_markdown": "# 새 본문",
            "deadline_at": None,
        }
        client = make_fixed_client(json.dumps(payload, ensure_ascii=False))
        result = enrich_notice(self.notice, client=client, force=True)

        self.assertEqual(result["status"], "enriched")
        self.notice.refresh_from_db()
        self.assertEqual(self.notice.summary, payload["summary"])
        self.assertIsNone(self.notice.deadline_at)

    @override_settings(LLM_API_KEY="")
    def test_enrich_offline_fallback_without_key(self) -> None:
        # 키 없음 → get_client() 비활성 → 오프라인 폴백(요약=본문 앞부분, md=원문)
        result = enrich_notice(self.notice)

        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["provider"], PROVIDER_FALLBACK)
        self.assertFalse(result["deadline_at"])

        self.notice.refresh_from_db()
        self.assertTrue(self.notice.summary)  # 본문 앞부분으로 채워짐
        self.assertIn("장학금", self.notice.summary)
        self.assertEqual(
            self.notice.content_markdown, self.notice.content.strip()
        )
        self.assertIsNone(self.notice.deadline_at)

    def test_enrich_defensive_parse_of_codefenced_response(self) -> None:
        payload = {
            "summary": "요약 1. 요약 2. 요약 3.",
            "content_markdown": "# 제목",
            "deadline_at": None,
        }
        fenced = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        client = make_fixed_client(fenced)
        result = enrich_notice(self.notice, client=client)

        self.assertEqual(result["status"], "enriched")
        self.notice.refresh_from_db()
        self.assertEqual(self.notice.summary, payload["summary"])
        self.assertEqual(self.notice.content_markdown, "# 제목")

    def test_enrich_llm_failure_falls_back_and_saves(self) -> None:
        # 키 있으나 API 500 → enrich() 내부에서 오프라인 폴백 전환(예외 전파 없음)
        client = make_fixed_client("irrelevant", status_code=500)
        result = enrich_notice(self.notice, client=client)

        self.assertEqual(result["status"], "fallback")
        self.notice.refresh_from_db()
        self.assertEqual(
            self.notice.content_markdown, self.notice.content.strip()
        )
        self.assertIsNone(self.notice.deadline_at)

    def test_enrich_notices_batch_skips_already_enriched(self) -> None:
        n2 = Notice.objects.create(
            source_id=self.source,
            url="https://example.com/scholarship/2",
            title="두 번째 공지",
            content="첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다.",
            publisher="학생지원팀",
        )
        # 첫 공지는 이미 보강됨 → skip 대상(NFR-6)
        self.notice.summary = "이미 보강됨."
        self.notice.save(update_fields=["summary"])

        payload = {
            "summary": "a. b. c.",
            "content_markdown": "# x",
            "deadline_at": None,
        }
        client = make_fixed_client(json.dumps(payload, ensure_ascii=False))
        counts = enrich_notices([self.notice, n2], client=client)

        self.assertEqual(counts["processed"], 2)
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["enriched"], 1)

        n2.refresh_from_db()
        self.assertEqual(n2.summary, "a. b. c.")


class ParseDeadlineUnitTests(TestCase):
    def test_none_and_nullish_return_none(self) -> None:
        self.assertIsNone(parse_deadline(None))
        self.assertIsNone(parse_deadline("null"))
        self.assertIsNone(parse_deadline("없음"))
        self.assertIsNone(parse_deadline("미정"))
        self.assertIsNone(parse_deadline(""))

    def test_iso_date(self) -> None:
        d = parse_deadline("2026-03-15")
        self.assertIsNotNone(d)
        self.assertEqual((d.year, d.month, d.day), (2026, 3, 15))
        self.assertTrue(timezone.is_aware(d))

    def test_iso_datetime(self) -> None:
        d = parse_deadline("2026-03-15T18:30:00")
        self.assertIsNotNone(d)
        self.assertEqual(
            (d.year, d.month, d.day, d.hour, d.minute), (2026, 3, 15, 18, 30)
        )
        self.assertTrue(timezone.is_aware(d))

    def test_fuzzy_slash_format(self) -> None:
        d = parse_deadline("2026/03/15")  # ISO 파서 실패 → dateutil 폴백
        self.assertIsNotNone(d)
        self.assertEqual((d.year, d.month, d.day), (2026, 3, 15))
        self.assertTrue(timezone.is_aware(d))

    def test_unparseable_returns_none(self) -> None:
        self.assertIsNone(parse_deadline("언젠가 곧"))


class RecommendationReasonTests(BaseFixtures):
    """추천 reason 이 키워드 나열이 아니라 문장형 설명으로 저장되는지 + summary 활용."""

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_reason_is_sentence_form_and_summary_is_fed(self) -> None:
        # 공지에 보강 요약을 부여 → recommendation 입력(user 메시지)에 실려야 한다.
        self.notice.summary = (
            "신입 백엔드 개발자를 채용합니다. Django/REST API 실무를 담당합니다. "
            "지원 마감은 3월입니다."
        )
        self.notice.save(update_fields=["summary"])

        reason = (
            "Django 와 REST API 서버를 다루는 신입 백엔드 채용으로, 백엔드에 관심 있는 "
            "회원님의 커리어 방향과 정확히 맞습니다. 실무 역량을 쌓기 좋은 기회입니다."
        )
        payload = {
            "relevant": True,
            "score": 0.9,
            "matched_keywords": ["채용"],
            "reason": reason,
        }
        client, captured = make_capturing_client(payload)
        classify_notice(self.notice, client=client)

        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        # reason 이 그대로 저장되고, 문장형(공백 포함·충분한 길이)이며 키워드 나열이 아님.
        self.assertEqual(row.reason, reason)
        self.assertGreater(len(row.reason), 20)
        self.assertIn(" ", row.reason.strip())
        self.assertNotEqual(row.reason, ", ".join(payload["matched_keywords"]))
        # 보강 summary 가 recommendation 프롬프트에 포함됨(비용↓·품질↑).
        self.assertIn("핵심 요약", captured["user"])
        self.assertIn("신입 백엔드 개발자를 채용합니다", captured["user"])

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_recommendation_without_summary_omits_summary_block(self) -> None:
        # summary 가 없으면 요약 블록 없이도 정상 동작(하위호환).
        self.assertEqual(self.notice.summary, "")
        payload = {
            "relevant": True,
            "score": 0.8,
            "matched_keywords": ["채용"],
            "reason": "신입 백엔드 채용 공고로 회원님의 관심사에 부합합니다.",
        }
        client, captured = make_capturing_client(payload)
        classify_notice(self.notice, client=client)

        self.assertNotIn("핵심 요약", captured["user"])
        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertTrue(row.reason)


class BuildMessagesInterestTests(TestCase):
    """관심 조건(키워드+설명)이 실제 프롬프트에 실리는지 검증(사용자 우려 대응)."""

    def test_every_interest_keyword_and_description_flows_into_prompt(self) -> None:
        interests = [
            {"keyword": "채용", "description": "신입 백엔드 채용 공고", "priority": 5},
            {"keyword": "장학금", "description": "교내 성적우수 장학금 안내", "priority": 3},
        ]
        messages = build_messages(
            title="제목",
            content="본문",
            publisher="ACME",
            profile={"age": 26, "job": "백엔드 개발자"},
            interests=interests,
            summary="",
        )
        user_prompt = messages[-1]["content"]
        # 모든 관심 조건의 키워드와 설명이 프롬프트(user 메시지)에 포함되어야 한다.
        for interest in interests:
            self.assertIn(interest["keyword"], user_prompt)
            self.assertIn(interest["description"], user_prompt)


@override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
class IsRecommendedStorageTests(BaseFixtures):
    """store-all: 임계값 미만도 저장하되 is_recommended=False, 이상은 True."""

    def test_below_threshold_creates_row_marked_not_recommended(self) -> None:
        low_client = make_fixed_client(
            json.dumps(
                {
                    "relevant": False,
                    "score": 0.3,
                    "matched_keywords": [],
                    "reason": "약한 관련",
                }
            )
        )
        classify_notice(self.notice, client=low_client)

        # 삭제되지 않고 저장되며 is_recommended=False.
        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertFalse(row.is_recommended)
        self.assertAlmostEqual(row.relevance_score, 0.3)

    def test_above_threshold_creates_row_marked_recommended(self) -> None:
        high_client = make_fixed_client(
            json.dumps(
                {
                    "relevant": True,
                    "score": 0.8,
                    "matched_keywords": ["채용"],
                    "reason": "강한 관련",
                }
            )
        )
        classify_notice(self.notice, client=high_client)

        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertTrue(row.is_recommended)
        self.assertAlmostEqual(row.relevance_score, 0.8)


class FallbackDescriptionMatchTests(TestCase):
    """degraded/quota 폴백이 keyword 뿐 아니라 interest description 토큰도 매칭한다."""

    @override_settings(LLM_API_KEY="")
    def test_description_token_matches_when_keyword_does_not(self) -> None:
        client = LLMClient(api_key="")  # 비활성 → 결정론적 폴백 경로
        verdict = client.classify(
            title="사내 LLM 리서치 세미나",
            content="최신 AI research 동향을 공유합니다.",
            interests=[{"keyword": "동아리", "description": "AI research 관심"}],
        )

        # keyword('동아리')는 본문에 없지만 description 토큰(AI/research)이 매칭되어 추천.
        self.assertEqual(verdict.provider, PROVIDER_FALLBACK)
        self.assertGreaterEqual(verdict.score, 0.5)
        lowered = [k.lower() for k in verdict.matched_keywords]
        self.assertTrue(
            any(tok in lowered for tok in ("research", "ai")),
            verdict.matched_keywords,
        )
        self.assertNotIn("동아리", verdict.matched_keywords)
