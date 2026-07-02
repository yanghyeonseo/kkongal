"""sources 앱 테스트 — 사이트 카탈로그 · 온디맨드 동기화 · 유저 스코프 선별 · 스케줄러.

테스트 안전 규칙 준수: 실제 크롤/네트워크/이메일/LLM 없음.
- LLM 은 ``LLM_API_KEY=""`` 로 키워드 폴백만 사용(네트워크 0).
- 크롤은 ``NoticeCrawlService.crawl_site`` 를 목킹(사이트 접속 0).
- 이메일은 ``locmem`` 백엔드(실발송 0), 슬랙 채널은 만들지 않는다.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from account.models import Interest
from ai.service import classify_notices_for_user
from crawler.config_loader import load_config
from crawler.schemas import CrawlReport
from crawler.service import NoticeCrawlService
from notices.models import InboxNotice, Notice
from sources.models import NoticeSource, SourceSubscription
from sources.views import SourceCatalogView, SourceSyncView

User = get_user_model()

# crawler/config/sites.json 에 실제로 존재하는 지원 사이트 url + 그 config id.
SUPPORTED_URL = "https://cse.snu.ac.kr/community/notice"
SUPPORTED_SITE_ID = "snu_cse_notice"
OTHER_SUPPORTED_URL = "https://www.saramin.co.kr/zf_user/jobs/hot100"
# config 에 없는 임의 url(자동 수집 미지원).
UNSUPPORTED_URL = "https://example.com/custom-board"


def _report(*, fetched: int, inserted: int, duplicates: int = 0, errors=None) -> CrawlReport:
    return CrawlReport(
        source_id=SUPPORTED_SITE_ID,
        fetched=fetched,
        inserted=inserted,
        duplicates=duplicates,
        errors=list(errors or []),
        started_at=CrawlReport.now_iso(),
        finished_at=CrawlReport.now_iso(),
    )


class CatalogViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="cataloger", email="c@example.com")

    def _get(self, user=None):
        request = self.factory.get("/api/sources/catalog/")
        if user is not None:
            force_authenticate(request, user=user)
        return SourceCatalogView.as_view()(request)

    def test_catalog_lists_all_enabled_config_sites_for_anonymous(self) -> None:
        response = self._get()
        self.assertEqual(response.status_code, 200)

        expected = len(list(load_config().enabled_sites()))
        self.assertEqual(len(response.data), expected)

        item = response.data[0]
        self.assertEqual(
            set(item.keys()), {"name", "url", "category", "subscribed", "source_id"}
        )
        # 익명 사용자는 모든 항목이 미구독이고 아직 NoticeSource 도 없다.
        self.assertTrue(all(entry["subscribed"] is False for entry in response.data))
        self.assertTrue(all(entry["source_id"] is None for entry in response.data))

    def test_catalog_reflects_subscription_and_source_id_when_authed(self) -> None:
        source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        SourceSubscription.objects.create(user_id=self.user, source_id=source)

        response = self._get(user=self.user)
        self.assertEqual(response.status_code, 200)

        by_url = {entry["url"]: entry for entry in response.data}
        subscribed_entry = by_url[SUPPORTED_URL]
        self.assertTrue(subscribed_entry["subscribed"])
        self.assertEqual(subscribed_entry["source_id"], source.id)

        # 구독하지 않은 다른 사이트는 미구독으로 표시된다.
        other = by_url[OTHER_SUPPORTED_URL]
        self.assertFalse(other["subscribed"])
        self.assertIsNone(other["source_id"])


@override_settings(LLM_API_KEY="", LLM_RELEVANCE_THRESHOLD=0.5)
class ClassifyNoticesForUserTests(TestCase):
    def setUp(self) -> None:
        self.source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        self.user_a = User.objects.create_user(
            username="ua", email="ua@example.com", job="백엔드"
        )
        self.user_b = User.objects.create_user(
            username="ub", email="ub@example.com", job="백엔드"
        )
        for user in (self.user_a, self.user_b):
            Interest.objects.create(
                user_id=user, keyword="채용", description="채용 공고", priority=5
            )
            SourceSubscription.objects.create(user_id=user, source_id=self.source)
        self.notice = Notice.objects.create(
            source_id=self.source,
            url=f"{SUPPORTED_URL}/1",
            title="2026 백엔드 채용 공고",
            content="백엔드 개발자 채용",
            publisher="SNU",
            published_at=timezone.now(),
        )

    def test_only_classifies_the_given_user(self) -> None:
        summary = classify_notices_for_user(self.user_a, [self.notice])

        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["notices_processed"], 1)
        self.assertTrue(
            InboxNotice.objects.filter(
                user_id=self.user_a, notice_id=self.notice
            ).exists()
        )
        # 다른 구독자(user_b)의 inbox 는 절대 건드리지 않는다.
        self.assertFalse(
            InboxNotice.objects.filter(user_id=self.user_b).exists()
        )

    def test_idempotent_skips_already_classified(self) -> None:
        classify_notices_for_user(self.user_a, [self.notice])
        summary = classify_notices_for_user(self.user_a, [self.notice])

        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["skipped_existing"], 1)
        self.assertEqual(
            InboxNotice.objects.filter(
                user_id=self.user_a, notice_id=self.notice
            ).count(),
            1,
        )

    def test_never_touches_notified_at(self) -> None:
        classify_notices_for_user(self.user_a, [self.notice])
        row = InboxNotice.objects.get(user_id=self.user_a, notice_id=self.notice)
        sent_at = timezone.now()
        row.notified_at = sent_at
        row.save(update_fields=["notified_at"])

        # 재판정으로 점수/사유가 갱신돼도 notified_at 은 보존되어야 한다.
        classify_notices_for_user(self.user_a, [self.notice], reclassify=True)
        row.refresh_from_db()
        self.assertEqual(row.notified_at, sent_at)


@override_settings(LLM_API_KEY="", LLM_RELEVANCE_THRESHOLD=0.5)
class SyncViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        self.user = User.objects.create_user(
            username="syncer", email="s@example.com", job="백엔드"
        )
        Interest.objects.create(
            user_id=self.user, keyword="채용", description="채용 공고", priority=5
        )
        SourceSubscription.objects.create(user_id=self.user, source_id=self.source)

    def _sync(self, source_id, user=None):
        request = self.factory.post(f"/api/sources/{source_id}/sync/")
        if user is not None:
            force_authenticate(request, user=user)
        return SourceSyncView.as_view()(request, source_id=source_id)

    def _make_notice(self, suffix, *, title="백엔드 채용 공고", published_delta=None):
        published_at = None
        if published_delta is not None:
            published_at = timezone.now() - published_delta
        return Notice.objects.create(
            source_id=self.source,
            url=f"{SUPPORTED_URL}/{suffix}",
            title=title,
            content="백엔드 개발자 채용",
            publisher="SNU",
            published_at=published_at,
        )

    def test_requires_authentication(self) -> None:
        response = self._sync(self.source.id)
        self.assertEqual(response.status_code, 401)

    def test_source_not_found_returns_404(self) -> None:
        response = self._sync(999999, user=self.user)
        self.assertEqual(response.status_code, 404)

    def test_unsubscribed_user_forbidden(self) -> None:
        stranger = User.objects.create_user(username="stranger", email="x@example.com")
        response = self._sync(self.source.id, user=stranger)
        self.assertEqual(response.status_code, 403)

    def test_unsupported_url_returns_400(self) -> None:
        other = NoticeSource.objects.create(name="임의", url=UNSUPPORTED_URL)
        SourceSubscription.objects.create(user_id=self.user, source_id=other)
        response = self._sync(other.id, user=self.user)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "이 사이트는 자동 수집을 지원하지 않아요.")

    def test_crawls_and_classifies_new_notice(self) -> None:
        # crawl_site 를 목킹: 실제 사이트 접속 없이 매칭 공지 1건을 저장하고 리포트 반환.
        def fake_crawl(*_args, **_kwargs):
            self._make_notice("new-1", published_delta=timedelta(minutes=1))
            return _report(fetched=1, inserted=1)

        with patch.object(NoticeCrawlService, "crawl_site", side_effect=fake_crawl) as mocked:
            response = self._sync(self.source.id, user=self.user)

        mocked.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["crawled"])
        self.assertEqual(response.data["fetched"], 1)
        self.assertEqual(response.data["new_notices"], 1)
        self.assertEqual(response.data["inbox_added"], 1)
        self.assertEqual(InboxNotice.objects.filter(user_id=self.user).count(), 1)

    def test_rate_limited_skips_crawl_but_reclassifies_existing(self) -> None:
        # 최근에 크롤됨 → 재크롤 생략, 기존 미분류 공지만 이 사용자에 대해 선별.
        self.source.crawled_at = timezone.now()
        self.source.save(update_fields=["crawled_at"])
        self._make_notice("existing-1", published_delta=timedelta(hours=1))

        with patch.object(NoticeCrawlService, "crawl_site") as mocked:
            response = self._sync(self.source.id, user=self.user)

        mocked.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["crawled"])
        self.assertEqual(response.data["fetched"], 0)
        self.assertEqual(response.data["new_notices"], 0)
        self.assertEqual(response.data["inbox_added"], 1)

    def test_respects_10_cap_and_24h_window(self) -> None:
        self.source.crawled_at = timezone.now()  # 재크롤 생략(순수 선별만 검증)
        self.source.save(update_fields=["crawled_at"])

        # 24h 이내 매칭 공지 12건 + 24h 밖 매칭 공지 1건.
        for i in range(12):
            self._make_notice(f"recent-{i}", published_delta=timedelta(minutes=i + 1))
        stale = self._make_notice("stale", published_delta=timedelta(hours=30))

        response = self._sync(self.source.id, user=self.user)

        self.assertEqual(response.status_code, 200)
        # 최대 10건만 선별된다(비용 상한).
        self.assertEqual(response.data["inbox_added"], 10)
        self.assertEqual(InboxNotice.objects.filter(user_id=self.user).count(), 10)
        # 24h 밖 공지는 선별 대상에서 제외된다.
        self.assertFalse(
            InboxNotice.objects.filter(
                user_id=self.user, notice_id=stale
            ).exists()
        )

    def test_live_crawl_failure_is_graceful_not_500(self) -> None:
        # 라이브 사이트 장애(예외)여도 500 대신 crawled=false + 안내 메시지로 200.
        with patch.object(
            NoticeCrawlService, "crawl_site", side_effect=RuntimeError("boom")
        ):
            response = self._sync(self.source.id, user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["crawled"])
        self.assertEqual(response.data["inbox_added"], 0)
        self.assertIn("가져오지 못했어요", response.data["message"])

    def test_crawl_reporting_errors_with_zero_fetched_is_graceful(self) -> None:
        # crawl_site 가 예외를 삼켜 errors 만 담아 돌려줘도(장애) graceful 처리.
        with patch.object(
            NoticeCrawlService,
            "crawl_site",
            side_effect=lambda *a, **k: _report(fetched=0, inserted=0, errors=["fetch failed"]),
        ):
            response = self._sync(self.source.id, user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["crawled"])


@override_settings(
    LLM_API_KEY="",
    LLM_RELEVANCE_THRESHOLD=0.5,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class SchedulerCommandTests(TestCase):
    def setUp(self) -> None:
        # crawled_at=None → due. url 은 config 지원 사이트로 매핑된다.
        self.source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        self.user = User.objects.create_user(
            username="sched", email="sched@example.com", job="백엔드"
        )
        Interest.objects.create(
            user_id=self.user, keyword="채용", description="채용 공고", priority=5
        )
        SourceSubscription.objects.create(user_id=self.user, source_id=self.source)
        # 크롤은 목킹하므로, 선별할 신규 공지는 미리 시드한다(미분류 상태).
        self.notice = Notice.objects.create(
            source_id=self.source,
            url=f"{SUPPORTED_URL}/seed",
            title="백엔드 채용 공고",
            content="백엔드 개발자 채용",
            publisher="SNU",
            published_at=timezone.now(),
        )

    def test_once_runs_full_pipeline_without_network(self) -> None:
        out = StringIO()
        with patch.object(
            NoticeCrawlService,
            "crawl_site",
            side_effect=lambda *a, **k: _report(fetched=0, inserted=0),
        ) as mocked:
            call_command("run_scheduler", "--once", stdout=out, stderr=StringIO())

        # due 사이트가 크롤 대상으로 잡혔다.
        mocked.assert_called_once()
        # 선별 단계가 시드 공지를 매칭 사용자 inbox 로 편입했다.
        self.assertTrue(
            InboxNotice.objects.filter(
                user_id=self.user, notice_id=self.notice
            ).exists()
        )
        self.assertIn("틱 완료", out.getvalue())

    def test_once_with_no_due_sources_skips_crawl(self) -> None:
        # 모든 사이트를 방금 크롤한 것으로 표시 → due 없음.
        self.source.crawled_at = timezone.now()
        self.source.save(update_fields=["crawled_at"])

        out = StringIO()
        with patch.object(NoticeCrawlService, "crawl_site") as mocked:
            call_command("run_scheduler", "--once", stdout=out, stderr=StringIO())

        mocked.assert_not_called()
        self.assertIn("크롤 대상(due) 사이트 없음", out.getvalue())
