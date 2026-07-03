"""SourceCatalogView.get 커스텀(사용자 등록) 사이트 병합 테스트.

레시피가 확정된(scraper_kind 존재) 사용자 등록 사이트만 카탈로그에 노출되고, 내장
config 사이트와 같은 게시판(normalized_url 동일)은 내장이 우선해 중복 노출되지
않는지, 구독 여부가 사용자별로 정확히 표시되는지 검증한다.

테스트 안전 규칙 준수: 실제 크롤/네트워크/이메일/LLM 없음(DB 픽스처만 사용).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from crawler.config_loader import load_config
from sources.models import NoticeSource, SourceSubscription
from sources.views import SourceCatalogView

User = get_user_model()

# crawler/config/sites.json 에 실제로 존재하는 지원 사이트 url.
SUPPORTED_URL = "https://cse.snu.ac.kr/community/notice"
# 커스텀(비내장) 임의 url.
CUSTOM_URL = "https://recruit.example-corp.com/notices"
CUSTOM_URL_2 = "https://jobs.another-corp.com/board"


class CatalogCustomSourceTests(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="cataloger2", email="c2@example.com"
        )
        self.other_user = User.objects.create_user(
            username="other2", email="o2@example.com"
        )
        self.config = load_config()

    def _get(self, user=None):
        request = self.factory.get("/api/sources/catalog/")
        if user is not None:
            force_authenticate(request, user=user)
        return SourceCatalogView.as_view()(request)

    def _by_url(self, response):
        return {entry["url"]: entry for entry in response.data}

    def test_confirmed_custom_source_appears_with_custom_true(self) -> None:
        source = NoticeSource.objects.create(
            name="예시 회사 채용 공지",
            url=CUSTOM_URL,
            category="채용",
            scraper_kind="rss",
            extraction_profile={"feed": f"{CUSTOM_URL}/feed"},
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)

        by_url = self._by_url(response)
        self.assertIn(CUSTOM_URL, by_url)
        entry = by_url[CUSTOM_URL]
        self.assertEqual(entry["name"], "예시 회사 채용 공지")
        self.assertEqual(entry["category"], "채용")
        self.assertEqual(entry["source_id"], source.id)
        self.assertTrue(entry["custom"])

    def test_unconfirmed_custom_source_is_excluded(self) -> None:
        NoticeSource.objects.create(
            name="미확정 사이트",
            url=CUSTOM_URL,
            category="etc",
            scraper_kind="",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)

        by_url = self._by_url(response)
        self.assertNotIn(CUSTOM_URL, by_url)

    def test_builtin_config_sites_still_appear_with_custom_false(self) -> None:
        response = self._get()
        self.assertEqual(response.status_code, 200)

        by_url = self._by_url(response)
        self.assertIn(SUPPORTED_URL, by_url)
        self.assertFalse(by_url[SUPPORTED_URL]["custom"])

    def test_custom_source_matching_builtin_normalized_url_is_not_duplicated(
        self,
    ) -> None:
        # www. 접두사·끝 슬래시만 다른 같은 게시판 — normalize_url 이 내장과 동일한
        # 정규화 키로 묶으므로 중복 노출되면 안 되고, 내장 항목이 우선한다.
        duplicate_url = "https://www.cse.snu.ac.kr/community/notice/"
        NoticeSource.objects.create(
            name="중복 커스텀",
            url=duplicate_url,
            category="etc",
            scraper_kind="rss",
            extraction_profile={"feed": "https://cse.snu.ac.kr/feed"},
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)

        # 내장 사이트가 가리키는 게시판은 정확히 한 번만 등장한다(내장 항목, custom=false).
        matches = [
            entry
            for entry in response.data
            if entry["url"] in (SUPPORTED_URL, duplicate_url)
        ]
        self.assertEqual(len(matches), 1)
        self.assertFalse(matches[0]["custom"])
        self.assertEqual(matches[0]["url"], SUPPORTED_URL)

    def test_subscribed_true_only_for_requesting_users_subscriptions(self) -> None:
        builtin_source = NoticeSource.objects.create(
            name="SNU CSE", url=SUPPORTED_URL
        )
        custom_source = NoticeSource.objects.create(
            name="커스텀",
            url=CUSTOM_URL,
            category="etc",
            scraper_kind="heuristic",
            extraction_profile={"row": ".item", "title": ".t", "link": "a"},
        )
        SourceSubscription.objects.create(
            user_id=self.user, source_id=builtin_source
        )
        SourceSubscription.objects.create(
            user_id=self.user, source_id=custom_source
        )

        response = self._get(user=self.user)
        self.assertEqual(response.status_code, 200)
        by_url = self._by_url(response)
        self.assertTrue(by_url[SUPPORTED_URL]["subscribed"])
        self.assertTrue(by_url[CUSTOM_URL]["subscribed"])

        other_response = self._get(user=self.other_user)
        self.assertEqual(other_response.status_code, 200)
        other_by_url = self._by_url(other_response)
        self.assertFalse(other_by_url[SUPPORTED_URL]["subscribed"])
        self.assertFalse(other_by_url[CUSTOM_URL]["subscribed"])

    def test_anonymous_request_returns_200_with_subscribed_false(self) -> None:
        NoticeSource.objects.create(
            name="커스텀",
            url=CUSTOM_URL_2,
            category="etc",
            scraper_kind="json_api",
            extraction_profile={"endpoint": CUSTOM_URL_2},
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(entry["subscribed"] is False for entry in response.data))
