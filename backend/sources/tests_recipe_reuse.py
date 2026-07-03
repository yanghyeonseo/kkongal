"""NoticeSource.resolve() dedup + 크롤 레시피 재사용 테스트.

핵심 스케일링 스토리: 한 게시판이 표기만 다른 URL 로 여러 번 등록돼도 하나의
NoticeSource 로 모이고, 먼저 학습된 크롤 레시피(extraction_profile 등)를 다음
구독자가 재크롤 없이 그대로 재사용한다.
"""
from __future__ import annotations

from django.test import TestCase

from sources.models import NoticeSource


class ResolveDedupTests(TestCase):
    """resolve() 는 정규화 URL 을 키로 같은 게시판을 하나의 row 로 모은다."""

    def test_equivalent_variant_urls_resolve_to_same_row(self) -> None:
        source1, created1 = NoticeSource.resolve("https://www.site.com/board/")
        source2, created2 = NoticeSource.resolve(
            "http://site.com/board?utm_source=x"
        )

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(source1.pk, source2.pk)
        self.assertEqual(NoticeSource.objects.count(), 1)


class RecipeReuseTests(TestCase):
    """확정된 크롤 레시피는 같은 게시판의 다음 구독자에게 그대로 재사용된다."""

    def test_confirmed_recipe_is_reused_by_equivalent_variant_url(self) -> None:
        # 1) 첫 구독자가 등록 → resolve 로 소스 생성.
        source, created = NoticeSource.resolve("https://www.site.com/board/")
        self.assertTrue(created)

        # 2) 첫 크롤이 성공해 크롤 레시피가 학습됐다고 가정.
        source.scraper_kind = "heuristic"
        source.extraction_profile = {"row": "table tbody tr"}
        source.render = "http"
        source.save()

        # 3) 두 번째 구독자가 표기만 다른(동치) URL 을 붙여넣는다.
        reused, created2 = NoticeSource.resolve("http://site.com/board?utm_source=x")

        self.assertFalse(created2)
        self.assertEqual(reused.pk, source.pk)
        # 학습된 레시피가 재크롤 없이 그대로 재사용된다.
        self.assertEqual(reused.scraper_kind, "heuristic")
        self.assertEqual(reused.extraction_profile, {"row": "table tbody tr"})
        self.assertEqual(reused.render, "http")
        self.assertTrue(reused.is_recipe_confirmed)
        self.assertEqual(NoticeSource.objects.count(), 1)

    def test_genuinely_different_board_creates_second_row(self) -> None:
        NoticeSource.resolve("https://www.site.com/board/")
        other, created = NoticeSource.resolve("https://www.site.com/other-board/")

        self.assertTrue(created)
        self.assertEqual(NoticeSource.objects.count(), 2)


class DirectCreateNormalizesUrlTests(TestCase):
    """직접 objects.create(url=...) 해도 save() 가 normalized_url 을 채운다."""

    def test_direct_create_autofills_normalized_url(self) -> None:
        source = NoticeSource.objects.create(url="https://www.site.com/board/")

        self.assertTrue(source.normalized_url)
        self.assertEqual(source.normalized_url, "https://site.com/board")

    def test_direct_create_with_distinct_url_does_not_collide(self) -> None:
        NoticeSource.objects.create(url="https://www.site.com/board/")
        other = NoticeSource.objects.create(url="https://www.site.com/other-board/")

        self.assertTrue(other.normalized_url)
        self.assertEqual(NoticeSource.objects.count(), 2)
