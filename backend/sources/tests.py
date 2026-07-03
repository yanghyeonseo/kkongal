"""sources 앱 테스트 — 사이트 카탈로그 · 온디맨드 동기화 · 유저 스코프 선별 · 스케줄러.

테스트 안전 규칙 준수: 실제 크롤/네트워크/이메일/LLM 없음.
- LLM 은 ``LLM_API_KEY=""`` 로 키워드 폴백만 사용(네트워크 0).
- 크롤은 ``NoticeCrawlService`` 의 크롤 메서드(sync=crawl_recent / 스케줄러=crawl_site)를
  목킹(사이트 접속 0). crawl_recent 는 be-crawler 가 병렬로 추가 중이라 ``create=True`` 로
  패치해 미배포 상태에서도 안전하게 목킹한다.
- 이메일은 ``locmem`` 백엔드(실발송 0), 슬랙 채널은 만들지 않는다.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
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
from sources import sync_jobs
from sources.models import NoticeSource, SourceSubscription
from sources.views import (
    SourceCatalogView,
    SourceDetailView,
    SourceSubscriptionListView,
    SourceSyncStatusView,
    SourceSyncView,
)

User = get_user_model()

# crawler/config/sites.json 에 실제로 존재하는 지원 사이트 url + 그 config id.
SUPPORTED_URL = "https://cse.snu.ac.kr/community/notice"
SUPPORTED_SITE_ID = "snu_cse_notice"
SUPPORTED_HOST = "cse.snu.ac.kr"
SUPPORTED_NAME = "서울대 컴퓨터공학부 공지"  # sites.json 의 사람이 읽는 이름.
OTHER_SUPPORTED_URL = "https://www.saramin.co.kr/zf_user/jobs/hot100"
# config 에 없는 임의 url(자동 수집 미지원).
UNSUPPORTED_URL = "https://example.com/custom-board"
UNSUPPORTED_HOST = "example.com"


def _favicon(host: str) -> str:
    """Google s2 파비콘 URL(구현이 만들어야 하는 정확한 형태)."""
    return f"https://www.google.com/s2/favicons?domain={host}&sz=64"


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
            set(item.keys()),
            {"name", "url", "category", "favicon_url", "subscribed", "source_id", "custom"},
        )
        # 카탈로그 항목은 URL 로부터 계산한 파비콘을 담는다(네트워크 없음).
        by_url = {entry["url"]: entry for entry in response.data}
        self.assertEqual(
            by_url[SUPPORTED_URL]["favicon_url"], _favicon(SUPPORTED_HOST)
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


class SubscribeViewTests(TestCase):
    """POST /api/subscriptions/ — 표시명·파비콘을 URL 만으로 채운다(네트워크 없음)."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="sub", email="sub@example.com")

    def _post(self, url, user=None):
        request = self.factory.post(
            "/api/subscriptions/", {"url": url}, format="json"
        )
        if user is not None:
            force_authenticate(request, user=user)
        return SourceSubscriptionListView.as_view()(request)

    def test_requires_authentication(self) -> None:
        response = self._post(SUPPORTED_URL)
        self.assertEqual(response.status_code, 401)

    def test_subscribe_sets_favicon_and_catalog_name(self) -> None:
        response = self._post(SUPPORTED_URL, user=self.user)
        self.assertIn(response.status_code, (200, 201))

        source = NoticeSource.objects.get(url=SUPPORTED_URL)
        # 파비콘은 호스트 기반 Google s2 URL 로 저장된다.
        self.assertEqual(source.favicon_url, _favicon(SUPPORTED_HOST))
        # 카탈로그 사이트면 config 의 사람이 읽는 이름을 표시명으로 쓴다.
        self.assertEqual(source.name, SUPPORTED_NAME)
        # 응답에 실린 source 에도 favicon_url + friendly name 이 포함된다.
        self.assertEqual(
            response.data["source"]["favicon_url"], _favicon(SUPPORTED_HOST)
        )
        self.assertEqual(response.data["source"]["name"], SUPPORTED_NAME)

    def test_subscribe_derives_name_from_domain_for_non_catalog(self) -> None:
        response = self._post(UNSUPPORTED_URL, user=self.user)
        self.assertIn(response.status_code, (200, 201))

        source = NoticeSource.objects.get(url=UNSUPPORTED_URL)
        self.assertEqual(source.favicon_url, _favicon(UNSUPPORTED_HOST))
        # 카탈로그에 없으면 도메인에서 읽기 쉬운 이름을 만든다.
        self.assertEqual(source.name, UNSUPPORTED_HOST)

    def test_subscribe_backfills_existing_source_when_empty(self) -> None:
        # 크롤러가 먼저 만든(표시명/파비콘 비어 있는) source 를 구독하면 채워 넣는다.
        source = NoticeSource.objects.create(url=SUPPORTED_URL)
        self.assertEqual(source.name, "")
        self.assertEqual(source.favicon_url, "")

        self._post(SUPPORTED_URL, user=self.user)

        source.refresh_from_db()
        self.assertEqual(source.favicon_url, _favicon(SUPPORTED_HOST))
        self.assertEqual(source.name, SUPPORTED_NAME)


class SourceRenameViewTests(TestCase):
    """PATCH /api/sources/<id>/ — 구독자만 표시명을 편집한다."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.source = NoticeSource.objects.create(
            name="원래 이름",
            url=SUPPORTED_URL,
            favicon_url=_favicon(SUPPORTED_HOST),
        )
        self.owner = User.objects.create_user(
            username="owner", email="o@example.com"
        )
        SourceSubscription.objects.create(user_id=self.owner, source_id=self.source)

    def _patch(self, source_id, data, user=None):
        request = self.factory.patch(
            f"/api/sources/{source_id}/", data, format="json"
        )
        if user is not None:
            force_authenticate(request, user=user)
        return SourceDetailView.as_view()(request, source_id=source_id)

    def test_requires_authentication(self) -> None:
        response = self._patch(self.source.id, {"name": "새 이름"})
        self.assertEqual(response.status_code, 401)

    def test_source_not_found_returns_404(self) -> None:
        response = self._patch(999999, {"name": "새 이름"}, user=self.owner)
        self.assertEqual(response.status_code, 404)

    def test_non_subscriber_forbidden(self) -> None:
        stranger = User.objects.create_user(
            username="stranger", email="x@example.com"
        )
        response = self._patch(self.source.id, {"name": "새 이름"}, user=stranger)
        self.assertEqual(response.status_code, 403)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "원래 이름")

    def test_rename_success_returns_updated_source(self) -> None:
        response = self._patch(
            self.source.id, {"name": "  내 사이트  "}, user=self.owner
        )
        self.assertEqual(response.status_code, 200)
        # 앞뒤 공백은 정리되어 저장된다.
        self.assertEqual(response.data["name"], "내 사이트")
        # 응답에는 파비콘 등 전체 source 표현이 포함된다.
        self.assertEqual(response.data["favicon_url"], _favicon(SUPPORTED_HOST))
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "내 사이트")

    def test_empty_name_rejected(self) -> None:
        response = self._patch(self.source.id, {"name": "   "}, user=self.owner)
        self.assertEqual(response.status_code, 400)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "원래 이름")

    def test_too_long_name_rejected(self) -> None:
        response = self._patch(
            self.source.id, {"name": "가" * 129}, user=self.owner
        )
        self.assertEqual(response.status_code, 400)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "원래 이름")


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
        # LLM 으로 확정된 쌍(classified_by_llm=True)만 재판정 없이 생략된다. (폴백 행은
        # 아직 확정 전이라 재처리 대상 — 폴백 고착 방지, ai 앱 테스트에서 검증.)
        InboxNotice.objects.create(
            user_id=self.user_a,
            notice_id=self.notice,
            relevance_score=0.9,
            reason="채용 공고로 판단",
            classified_by_llm=True,
        )
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
class RunSyncForSourceTests(TestCase):
    """sync_jobs.run_sync_for_source 직접 단위 테스트(오프라인).

    워커가 호출하는 실제 작업 로직: 크롤→보강→선별→발송. 크롤은 목킹(네트워크 0),
    알림 발송(dispatch_pending)도 목킹(이메일 0)해 결정적으로 검증한다.
    """

    def setUp(self) -> None:
        self.source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        self.user = User.objects.create_user(
            username="syncer", email="s@example.com", job="백엔드"
        )
        Interest.objects.create(
            user_id=self.user, keyword="채용", description="채용 공고", priority=5
        )
        SourceSubscription.objects.create(user_id=self.user, source_id=self.source)
        self.config = load_config()
        # 알림 발송은 워커 내부에서 동기 호출된다 — 실제 발송 대신 목킹해 트리거만 검증.
        patcher = patch("alert.service.dispatch_pending")
        self.mock_dispatch = patcher.start()
        self.addCleanup(patcher.stop)

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

    def _run(self):
        return sync_jobs.run_sync_for_source(self.user, self.source, self.config)

    def test_crawls_and_classifies_new_notice(self) -> None:
        # crawl_recent 를 목킹: 실제 사이트 접속 없이 매칭 공지 1건을 저장하고 리포트 반환.
        def fake_crawl(*_args, **_kwargs):
            self._make_notice("new-1", published_delta=timedelta(minutes=1))
            return _report(fetched=1, inserted=1)

        with patch.object(
            NoticeCrawlService, "crawl_recent", create=True, side_effect=fake_crawl
        ) as mocked:
            result = self._run()

        mocked.assert_called_once()
        self.assertTrue(result["crawled"])
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["new_notices"], 1)
        self.assertEqual(result["inbox_added"], 1)
        self.assertEqual(InboxNotice.objects.filter(user_id=self.user).count(), 1)

    def test_enriches_only_newly_created_notices(self) -> None:
        # 크롤 전 이미 존재하던 공지("old")는 보강 대상이 아니고, 이번에 새로 생긴
        # 공지("fresh")만 공지당 1회 보강으로 넘어간다.
        self._make_notice("old", published_delta=timedelta(hours=2))

        def fake_crawl(*_args, **_kwargs):
            self._make_notice("fresh", published_delta=timedelta(minutes=1))
            return _report(fetched=1, inserted=1)

        with patch.object(
            NoticeCrawlService, "crawl_recent", create=True, side_effect=fake_crawl
        ), patch.object(sync_jobs, "_enrich_new_notices") as enrich:
            self._run()

        enrich.assert_called_once()
        (enriched_qs,) = enrich.call_args.args
        enriched_urls = {notice.url for notice in enriched_qs}
        self.assertEqual(enriched_urls, {f"{SUPPORTED_URL}/fresh"})

    def test_rate_limited_skips_crawl_but_reclassifies_existing(self) -> None:
        # 최근에 크롤됨 → 재크롤 생략, 기존 미분류 공지만 이 사용자에 대해 선별.
        self.source.crawled_at = timezone.now()
        self.source.save(update_fields=["crawled_at"])
        self._make_notice("existing-1", published_delta=timedelta(hours=1))

        with patch.object(NoticeCrawlService, "crawl_recent", create=True) as mocked:
            result = self._run()

        mocked.assert_not_called()
        self.assertFalse(result["crawled"])
        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["new_notices"], 0)
        self.assertEqual(result["inbox_added"], 1)

    def test_classifies_at_most_10_most_recent(self) -> None:
        self.source.crawled_at = timezone.now()  # 재크롤 생략(순수 선별만 검증)
        self.source.save(update_fields=["crawled_at"])

        # 매칭 공지 12건(1~12분 전). 가장 최근 10건만 선별되고 오래된 2건은 제외된다.
        notices = [
            self._make_notice(f"recent-{i}", published_delta=timedelta(minutes=i + 1))
            for i in range(12)
        ]

        result = self._run()

        # 가장 최근 10건만 선별된다(비용 상한).
        self.assertEqual(result["inbox_added"], 10)
        self.assertEqual(InboxNotice.objects.filter(user_id=self.user).count(), 10)
        # 가장 오래된 2건(11·12번째)은 상한 밖이라 선별되지 않는다.
        for stale in notices[-2:]:
            self.assertFalse(
                InboxNotice.objects.filter(
                    user_id=self.user, notice_id=stale
                ).exists()
            )

    def test_dispatches_alerts_when_recommended(self) -> None:
        # 새 추천 공지가 생기면 이 사용자의 알림을 (워커 스레드 내) 동기로 발송한다.
        self.source.crawled_at = timezone.now()  # 재크롤 생략(순수 선별만)
        self.source.save(update_fields=["crawled_at"])
        self._make_notice("rec-1", published_delta=timedelta(minutes=1))

        result = self._run()

        self.assertEqual(result["inbox_added"], 1)
        self.mock_dispatch.assert_called_once_with(user=self.user)

    def test_skips_dispatch_when_nothing_recommended(self) -> None:
        # 추천이 0건이면(관심과 무관한 공지만) 발송하지 않는다.
        self.source.crawled_at = timezone.now()
        self.source.save(update_fields=["crawled_at"])
        Notice.objects.create(
            source_id=self.source,
            url=f"{SUPPORTED_URL}/nomatch-1",
            title="무관한 소식",
            content="오늘 날씨가 맑습니다",
            publisher="SNU",
            published_at=timezone.now() - timedelta(minutes=1),
        )

        result = self._run()

        self.assertEqual(result["inbox_added"], 0)
        self.mock_dispatch.assert_not_called()

    def test_live_crawl_failure_is_graceful(self) -> None:
        # 라이브 사이트 장애(예외)여도 예외 대신 crawled=false + 안내 메시지.
        with patch.object(
            NoticeCrawlService,
            "crawl_recent",
            create=True,
            side_effect=RuntimeError("boom"),
        ):
            result = self._run()

        self.assertFalse(result["crawled"])
        self.assertEqual(result["inbox_added"], 0)
        self.assertIn("가져오지 못했어요", result["message"])

    def test_crawl_reporting_errors_with_zero_fetched_is_graceful(self) -> None:
        # crawl_recent 가 예외를 삼켜 errors 만 담아 돌려줘도(장애) graceful 처리.
        with patch.object(
            NoticeCrawlService,
            "crawl_recent",
            create=True,
            side_effect=lambda *a, **k: _report(fetched=0, inserted=0, errors=["fetch failed"]),
        ):
            result = self._run()

        self.assertFalse(result["crawled"])


class SyncViewTests(TestCase):
    """POST /api/sources/<id>/sync/ — 동기 검증만 하고 작업을 enqueue 한 뒤 즉시 반환."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        self.user = User.objects.create_user(
            username="syncer", email="s@example.com", job="백엔드"
        )
        SourceSubscription.objects.create(user_id=self.user, source_id=self.source)
        # enqueue 는 데몬 워커를 띄우므로 뷰 계약 테스트에서는 목킹한다(스레드/네트워크 0).
        patcher = patch("sources.sync_jobs.enqueue")
        self.mock_enqueue = patcher.start()
        self.addCleanup(patcher.stop)

    def _sync(self, source_id, user=None):
        request = self.factory.post(f"/api/sources/{source_id}/sync/")
        if user is not None:
            force_authenticate(request, user=user)
        return SourceSyncView.as_view()(request, source_id=source_id)

    def test_requires_authentication(self) -> None:
        response = self._sync(self.source.id)
        self.assertEqual(response.status_code, 401)
        self.mock_enqueue.assert_not_called()

    def test_source_not_found_returns_404(self) -> None:
        response = self._sync(999999, user=self.user)
        self.assertEqual(response.status_code, 404)
        self.mock_enqueue.assert_not_called()

    def test_unsubscribed_user_forbidden(self) -> None:
        stranger = User.objects.create_user(username="stranger", email="x@example.com")
        response = self._sync(self.source.id, user=stranger)
        self.assertEqual(response.status_code, 403)
        self.mock_enqueue.assert_not_called()

    def test_arbitrary_url_enqueues_generic_sync(self) -> None:
        # 카탈로그에 없는 임의 URL 도 이제 generic 파이프라인으로 동기화된다(400 아님).
        other = NoticeSource.objects.create(name="임의", url=UNSUPPORTED_URL)
        SourceSubscription.objects.create(user_id=self.user, source_id=other)
        response = self._sync(other.id, user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "started", "source_id": other.id})
        self.mock_enqueue.assert_called_once_with(self.user, other)

    def test_sync_enqueues_and_returns_started(self) -> None:
        response = self._sync(self.source.id, user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {"status": "started", "source_id": self.source.id}
        )
        # 검증만 통과하면 실제 작업은 워커에 위임한다(요청 사용자·소스로 정확히 1회).
        self.mock_enqueue.assert_called_once_with(self.user, self.source)


class SyncStatusViewTests(TestCase):
    """GET /api/sources/sync/status/ — 구독 사이트들의 동기화 상태 맵(idle 은 생략)."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="poller", email="p@example.com")
        self.source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        self.other = NoticeSource.objects.create(name="사람인", url=OTHER_SUPPORTED_URL)
        SourceSubscription.objects.create(user_id=self.user, source_id=self.source)
        SourceSubscription.objects.create(user_id=self.user, source_id=self.other)
        cache.clear()
        self.addCleanup(cache.clear)

    def _get(self, user=None):
        request = self.factory.get("/api/sources/sync/status/")
        if user is not None:
            force_authenticate(request, user=user)
        return SourceSyncStatusView.as_view()(request)

    def test_requires_authentication(self) -> None:
        response = self._get()
        self.assertEqual(response.status_code, 401)

    def test_returns_cached_jobs_map(self) -> None:
        sync_jobs._set_status(
            self.user.id, self.source.id, "done", inbox_added=2, message="완료"
        )
        response = self._get(user=self.user)

        self.assertEqual(response.status_code, 200)
        jobs = response.data["jobs"]
        self.assertEqual(
            jobs[self.source.id],
            {"status": "done", "inbox_added": 2, "message": "완료"},
        )
        # 상태 엔트리가 없는 구독 사이트는 맵에서 생략된다(idle).
        self.assertNotIn(self.other.id, jobs)

    def test_scopes_status_to_requesting_user(self) -> None:
        # 상태 캐시 키는 사용자별이라 다른 사용자의 진행 상태가 섞이지 않는다.
        stranger = User.objects.create_user(username="stranger2", email="x2@example.com")
        sync_jobs._set_status(stranger.id, self.source.id, "running")

        response = self._get(user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["jobs"], {})


@override_settings(LLM_API_KEY="", LLM_RELEVANCE_THRESHOLD=0.5)
class SyncJobsWorkerTests(TestCase):
    """워커 per-작업 처리(_process_job)와 enqueue→_process_one seam.

    실제 데몬 워커 스레드는 띄우지 않는다(전역 상태·DB 스레드 경합 회피). 작업을 같은
    스레드에서 동기 처리하고, 스레드 로컬 DB 커넥션 close 는 목킹해 테스트 DB 를 지킨다.
    """

    def setUp(self) -> None:
        self.source = NoticeSource.objects.create(name="SNU CSE", url=SUPPORTED_URL)
        self.user = User.objects.create_user(
            username="worker", email="w@example.com", job="백엔드"
        )
        Interest.objects.create(
            user_id=self.user, keyword="채용", description="채용 공고", priority=5
        )
        SourceSubscription.objects.create(user_id=self.user, source_id=self.source)
        cache.clear()
        self.addCleanup(cache.clear)
        self.addCleanup(self._drain_queue)

    @staticmethod
    def _drain_queue() -> None:
        # 전역 큐에 남은 작업이 다른 테스트로 새지 않도록 (처리 없이) 비운다.
        q = sync_jobs._job_queue
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except Exception:  # noqa: BLE001
                break

    def _make_notice(self, suffix, *, published_delta=None):
        published_at = None
        if published_delta is not None:
            published_at = timezone.now() - published_delta
        return Notice.objects.create(
            source_id=self.source,
            url=f"{SUPPORTED_URL}/{suffix}",
            title="백엔드 채용 공고",
            content="백엔드 개발자 채용",
            publisher="SNU",
            published_at=published_at,
        )

    def test_process_job_sets_done_status(self) -> None:
        self.source.crawled_at = timezone.now()  # rate-limited → 크롤 없이 선별만
        self.source.save(update_fields=["crawled_at"])
        self._make_notice("rec-1", published_delta=timedelta(minutes=1))

        with patch("django.db.connection.close"), patch(
            "alert.service.dispatch_pending"
        ):
            sync_jobs._process_job((self.user.id, self.source.id))

        status_map = sync_jobs.get_status_for(self.user, [self.source.id])
        self.assertEqual(status_map[self.source.id]["status"], "done")
        self.assertEqual(status_map[self.source.id]["inbox_added"], 1)

    def test_process_job_sets_failed_status_on_error(self) -> None:
        # 작업 중 예외가 나도 워커는 죽지 않고 terminal 'failed' 상태를 남긴다.
        with patch("django.db.connection.close"), patch.object(
            sync_jobs, "run_sync_for_source", side_effect=RuntimeError("boom")
        ):
            sync_jobs._process_job((self.user.id, self.source.id))

        status_map = sync_jobs.get_status_for(self.user, [self.source.id])
        self.assertEqual(status_map[self.source.id]["status"], "failed")
        self.assertEqual(status_map[self.source.id]["message"], "동기화에 실패했어요.")

    def test_enqueue_sets_running_then_process_one_completes(self) -> None:
        # enqueue 는 즉시 'running' 을 세우고 큐에 넣는다(데몬 워커는 목킹으로 미기동).
        with patch.object(sync_jobs, "_ensure_worker") as ensure:
            sync_jobs.enqueue(self.user, self.source)
        ensure.assert_called_once()

        running = sync_jobs.get_status_for(self.user, [self.source.id])
        self.assertEqual(running[self.source.id]["status"], "running")

        # 큐에서 하나 꺼내 동기 처리하면 terminal 'done' 으로 전이한다.
        with patch("django.db.connection.close"), patch.object(
            sync_jobs,
            "run_sync_for_source",
            return_value={"inbox_added": 3, "message": "완료"},
        ) as run:
            self.assertTrue(sync_jobs._process_one(timeout=1))
        run.assert_called_once()

        done = sync_jobs.get_status_for(self.user, [self.source.id])
        self.assertEqual(done[self.source.id]["status"], "done")
        self.assertEqual(done[self.source.id]["inbox_added"], 3)
        self.assertEqual(done[self.source.id]["message"], "완료")

    def test_enqueue_dedups_while_running(self) -> None:
        # 이미 'running' 인 (user, source) 는 연타/재요청해도 큐에 중복으로 쌓이지 않는다.
        with patch.object(sync_jobs, "_ensure_worker"):
            sync_jobs.enqueue(self.user, self.source)
            sync_jobs.enqueue(self.user, self.source)
            sync_jobs.enqueue(self.user, self.source)
        self.assertEqual(sync_jobs._job_queue.qsize(), 1)

        # 진행 중 작업이 끝나면(→ 'done') 다시 enqueue 가 허용된다.
        with patch("django.db.connection.close"), patch.object(
            sync_jobs,
            "run_sync_for_source",
            return_value={"inbox_added": 0, "message": "완료"},
        ):
            self.assertTrue(sync_jobs._process_one(timeout=1))
        self.assertEqual(sync_jobs._job_queue.qsize(), 0)

        with patch.object(sync_jobs, "_ensure_worker"):
            sync_jobs.enqueue(self.user, self.source)
        self.assertEqual(sync_jobs._job_queue.qsize(), 1)


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
