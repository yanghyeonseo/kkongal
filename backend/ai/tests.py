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

from ai.llm import PROVIDER_FALLBACK, PROVIDER_LLM, LLMClient, extract_json
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
        self.assertEqual(summary.created, 0)

        row = InboxNotice.objects.get(id=naive.id)  # 같은 행이 갱신됨(중복 아님)
        self.assertAlmostEqual(row.relevance_score, 0.9)  # 1.0 → 0.9 로 override
        self.assertEqual(row.reason, "채용 공고로 판단")
        self.assertEqual(row.matched_keywords, "채용")
        self.assertEqual(
            InboxNotice.objects.filter(notice_id=self.notice).count(), 1
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
    def test_ai_override_below_threshold_removes_naive_false_positive(self) -> None:
        # 순진한 매처가 오탐(1.0)으로 만든 행을, AI 가 '관련 없음'으로 덮어쓰며 삭제.
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

        self.assertEqual(summary.downgraded, 1)
        self.assertFalse(InboxNotice.objects.filter(id=naive.id).exists())

    @override_settings(LLM_RELEVANCE_THRESHOLD=0.5)
    def test_reclassify_below_threshold_deletes_stale_row(self) -> None:
        # 먼저 관련 있음으로 분류되어 행이 생성됨.
        run_classification(client=make_smart_client(), threshold=0.5)
        self.assertTrue(
            InboxNotice.objects.filter(
                user_id=self.user_match, notice_id=self.notice
            ).exists()
        )
        # 재판정에서 점수가 임계값 밑으로 → 오래된 행 삭제(다운그레이드).
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

        self.assertEqual(summary.downgraded, 1)
        self.assertFalse(
            InboxNotice.objects.filter(
                user_id=self.user_match, notice_id=self.notice
            ).exists()
        )

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
