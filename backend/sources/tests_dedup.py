"""중복 소스 병합(backfill_normalized_urls) 테스트.

마이그레이션 0003 의 병합 경로 — 같은 게시판으로 정규화되는 여러 NoticeSource 를
하나로 합치고 구독/공지를 유니크 제약을 지키며 이관하는 로직을 검증한다.
(과거엔 이 경로가 테스트로 커버되지 않아 FK 대입 버그가 숨어 있었다.)
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from notices.models import Notice
from sources.dedup import backfill_normalized_urls
from sources.models import NoticeSource, SourceSubscription

User = get_user_model()


class BackfillMergeTests(TestCase):
    def _make_source(self, url, normalized_url):
        # normalized_url 을 명시해 save() 자동채움을 우회, 사전-정규화(중복 미병합) 상태를 재현.
        return NoticeSource.objects.create(url=url, normalized_url=normalized_url)

    def test_merges_duplicate_sources_and_reassigns_relations(self):
        alice = User.objects.create_user(username="alice", email="a@x.com")
        bob = User.objects.create_user(username="bob", email="b@x.com")

        # 두 소스는 표기만 다른 같은 게시판(정규화 시 동일 키)이지만, 저장된
        # normalized_url 은 서로 달라 아직 병합 전 상태다.
        survivor = self._make_source("https://www.demo.com/board/", "https://demo.com/board")
        dup = self._make_source("http://demo.com/board?utm_source=x", "http://demo.com/board")

        # alice 는 두 소스 모두 구독(→ dup 쪽 구독은 survivor 중복이라 삭제돼야 함).
        SourceSubscription.objects.create(user_id=alice, source_id=survivor)
        SourceSubscription.objects.create(user_id=alice, source_id=dup)
        # bob 은 dup 만 구독(→ survivor 로 이관돼야 함).
        SourceSubscription.objects.create(user_id=bob, source_id=dup)

        # survivor·dup 에 겹치는 공지(url 동일)와 dup 전용 공지.
        Notice.objects.create(source_id=survivor, url="https://demo.com/n/1", title="공지1")
        Notice.objects.create(source_id=dup, url="https://demo.com/n/1", title="공지1-중복")
        Notice.objects.create(source_id=dup, url="https://demo.com/n/2", title="공지2")

        backfill_normalized_urls(NoticeSource, SourceSubscription, Notice)

        # dup 은 병합되어 사라지고, 같은 정규화 키의 소스는 하나만 남는다.
        self.assertFalse(NoticeSource.objects.filter(id=dup.id).exists())
        self.assertEqual(NoticeSource.objects.count(), 1)
        survivor.refresh_from_db()
        self.assertEqual(survivor.normalized_url, "https://demo.com/board")

        # 구독: alice 는 survivor 하나(중복 제거), bob 도 survivor 로 이관 → 총 2건.
        self.assertEqual(SourceSubscription.objects.count(), 2)
        self.assertTrue(
            SourceSubscription.objects.filter(user_id=alice, source_id=survivor).exists()
        )
        self.assertTrue(
            SourceSubscription.objects.filter(user_id=bob, source_id=survivor).exists()
        )

        # 공지: url 중복분은 삭제, 전용 공지는 survivor 로 이관 → n/1, n/2 각 1건.
        urls = set(
            Notice.objects.filter(source_id=survivor).values_list("url", flat=True)
        )
        self.assertEqual(urls, {"https://demo.com/n/1", "https://demo.com/n/2"})
        self.assertEqual(Notice.objects.count(), 2)

    def test_no_duplicates_recomputes_keys(self):
        # 서로 다른 게시판(정규화 키 상이). placeholder 로 저장돼 있어도 backfill 이
        # 각자의 올바른 정규화 키로 다시 채우고, 병합 없이 2건 그대로 유지한다.
        a = self._make_source("https://one.com/b", "https://placeholder-a")
        b = self._make_source("https://two.com/b", "https://placeholder-b")

        backfill_normalized_urls(NoticeSource, SourceSubscription, Notice)

        self.assertEqual(NoticeSource.objects.count(), 2)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.normalized_url, "https://one.com/b")
        self.assertEqual(b.normalized_url, "https://two.com/b")
