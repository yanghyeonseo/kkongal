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

from account.models import Interest
from notices.models import InboxNotice, Notice
from sources.models import NoticeSource, SourceSubscription

from ai.llm import PROVIDER_FALLBACK, PROVIDER_LLM, LLMClient, extract_json
from ai.service import classify_notice, run_classification

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
        # 매칭 사용자는 inbox 생성
        self.assertTrue(
            InboxNotice.objects.filter(
                user_id=self.user_match, notice_id=self.notice
            ).exists()
        )
        # 비매칭 사용자는 생성 안 됨
        self.assertFalse(
            InboxNotice.objects.filter(
                user_id=self.user_nomatch, notice_id=self.notice
            ).exists()
        )
        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertGreaterEqual(row.relevance_score, 0.5)
        self.assertIn("채용", row.matched_keywords)
        self.assertIn("키워드 매칭", row.reason)

    def test_api_failure_falls_back(self) -> None:
        # 키는 있지만 API 가 500 → 폴백으로 전환(예외 전파 없음)
        client = make_fixed_client("irrelevant", status_code=500)
        summary = run_classification(client=client, threshold=0.5)

        self.assertEqual(summary.provider, PROVIDER_FALLBACK)
        self.assertTrue(
            InboxNotice.objects.filter(user_id=self.user_match).exists()
        )

    def test_skips_already_classified(self) -> None:
        first = classify_notice(self.notice)
        self.assertEqual(first.created, 1)

        second = classify_notice(self.notice)  # reclassify=False → 기존 쌍 생략
        self.assertEqual(second.skipped_existing, 1)  # user_match 생략
        self.assertEqual(second.candidates, 1)  # user_nomatch 만 재평가
        self.assertEqual(
            InboxNotice.objects.filter(notice_id=self.notice).count(), 1
        )

    def test_run_classification_default_excludes_classified_notice(self) -> None:
        run_classification()  # notice 분류됨
        # 두 번째 기본 실행은 이미 분류된 공지를 후보에서 제외 → 처리 0
        summary = run_classification()
        self.assertEqual(summary.notices_processed, 0)


class LLMPathTests(BaseFixtures):
    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_llm_path_creates_for_relevant_only(self) -> None:
        client = make_smart_client()
        summary = run_classification(client=client)

        self.assertEqual(summary.provider, PROVIDER_LLM)
        self.assertEqual(summary.llm_calls, 2)
        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.below_threshold, 1)

        row = InboxNotice.objects.get(
            user_id=self.user_match, notice_id=self.notice
        )
        self.assertAlmostEqual(row.relevance_score, 0.9)
        self.assertEqual(row.reason, "채용 공고로 판단")
        self.assertEqual(row.matched_keywords, "채용")
        self.assertFalse(
            InboxNotice.objects.filter(user_id=self.user_nomatch).exists()
        )

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_idempotent_update_or_create(self) -> None:
        client = make_smart_client()
        run_classification(client=client)
        # reclassify=True 로 같은 쌍 재판정 → 갱신(중복 생성 아님)
        summary = run_classification(client=client, reclassify=True)

        self.assertEqual(summary.updated, 1)
        self.assertEqual(summary.created, 0)
        self.assertEqual(
            InboxNotice.objects.filter(
                user_id=self.user_match, notice_id=self.notice
            ).count(),
            1,
        )

    def test_threshold_gating_blocks_low_score(self) -> None:
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

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.below_threshold, 2)
        self.assertFalse(InboxNotice.objects.exists())

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
    def test_score_out_of_range_is_clamped(self) -> None:
        content = json.dumps(
            {
                "relevant": True,
                "score": 4.2,  # 범위 밖
                "matched_keywords": "채용, 백엔드",  # 문자열 형태도 허용
                "reason": "과도한 점수",
            }
        )
        client = make_fixed_client(content)
        run_classification(client=client, threshold=0.5)

        row = InboxNotice.objects.get(user_id=self.user_match)
        self.assertLessEqual(row.relevance_score, 1.0)
        self.assertEqual(row.matched_keywords, "채용, 백엔드")


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
