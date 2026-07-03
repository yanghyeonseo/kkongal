"""sources.ai_naming 테스트 — AI 기반 사이트 이름/카테고리 자동 채우기.

테스트 안전 규칙 준수: 실제 LLM 호출 없음 — ``sources.ai_naming.get_client`` 를
mock.patch 로 대체해 네트워크 0 으로 검증한다.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from notices.models import Notice
from sources.ai_naming import autofill_source_metadata
from sources.models import NoticeSource
from sources.naming import friendly_name_for

URL = "https://example.com/board"


def _make_fake_client(*, enabled: bool = True, result: dict | None = None):
    """.enabled / .complete_json 을 가진 페이크 LLM 클라이언트를 만든다."""

    class FakeClient:
        def __init__(self):
            self.enabled = enabled
            self.calls = []

        def complete_json(self, messages, *, model=None):
            self.calls.append(messages)
            return {} if result is None else result

    return FakeClient()


class AutofillSourceMetadataTests(TestCase):
    def _make_source(self, **overrides) -> NoticeSource:
        defaults = dict(
            name=friendly_name_for(URL),
            url=URL,
            category="etc",
            ai_named=False,
        )
        defaults.update(overrides)
        return NoticeSource.objects.create(**defaults)

    def _make_titles(self, source: NoticeSource, titles: list[str]) -> None:
        for i, title in enumerate(titles):
            Notice.objects.create(
                source_id=source,
                url=f"{URL}/{i}",
                title=title,
            )

    def test_fills_name_and_category_from_titles_when_auto_generated(self) -> None:
        source = self._make_source()
        self._make_titles(source, ["2026학년도 장학생 모집 공고", "장학금 신청 안내"])
        fake_client = _make_fake_client(
            result={"name": "더드림코리아", "category": "scholarship"}
        )

        with patch("sources.ai_naming.get_client", return_value=fake_client):
            autofill_source_metadata(source)

        source.refresh_from_db()
        self.assertEqual(source.name, "더드림코리아")
        self.assertEqual(source.category, "scholarship")
        self.assertTrue(source.ai_named)
        self.assertEqual(len(fake_client.calls), 1)

    def test_does_not_overwrite_user_edited_name_but_sets_category(self) -> None:
        source = self._make_source(name="내가직접지은이름")
        self._make_titles(source, ["채용 공고"])
        fake_client = _make_fake_client(result={"name": "AI가 지은 이름", "category": "job"})

        with patch("sources.ai_naming.get_client", return_value=fake_client):
            autofill_source_metadata(source)

        source.refresh_from_db()
        self.assertEqual(source.name, "내가직접지은이름")
        self.assertEqual(source.category, "job")
        self.assertTrue(source.ai_named)

    def test_does_not_overwrite_already_set_real_category(self) -> None:
        source = self._make_source(category="job")
        self._make_titles(source, ["채용 공고"])
        fake_client = _make_fake_client(
            result={"name": "새이름", "category": "scholarship"}
        )

        with patch("sources.ai_naming.get_client", return_value=fake_client):
            autofill_source_metadata(source)

        source.refresh_from_db()
        self.assertEqual(source.category, "job")
        self.assertEqual(source.name, "새이름")
        self.assertTrue(source.ai_named)

    def test_ai_named_short_circuits_without_calling_llm(self) -> None:
        source = self._make_source(ai_named=True, name="이미채워진이름", category="job")
        fake_client = _make_fake_client(result={"name": "무시됨", "category": "etc"})

        with patch("sources.ai_naming.get_client", return_value=fake_client) as get_client_mock:
            autofill_source_metadata(source)
            get_client_mock.assert_not_called()

        source.refresh_from_db()
        self.assertEqual(source.name, "이미채워진이름")
        self.assertEqual(source.category, "job")
        self.assertTrue(source.ai_named)

    def test_disabled_client_is_noop(self) -> None:
        source = self._make_source()
        self._make_titles(source, ["공지 제목"])
        fake_client = _make_fake_client(enabled=False)

        with patch("sources.ai_naming.get_client", return_value=fake_client):
            autofill_source_metadata(source)

        source.refresh_from_db()
        self.assertFalse(source.ai_named)
        self.assertEqual(source.category, "etc")
        self.assertEqual(source.name, friendly_name_for(URL))
        self.assertEqual(len(fake_client.calls), 0)

    def test_unusable_empty_result_is_noop(self) -> None:
        source = self._make_source()
        self._make_titles(source, ["공지 제목"])
        fake_client = _make_fake_client(result={})

        with patch("sources.ai_naming.get_client", return_value=fake_client):
            autofill_source_metadata(source)

        source.refresh_from_db()
        self.assertFalse(source.ai_named)
        self.assertEqual(source.category, "etc")
        self.assertEqual(source.name, friendly_name_for(URL))

    def test_category_sanitization_strips_invalid_characters(self) -> None:
        source = self._make_source()
        self._make_titles(source, ["채용 공고"])
        fake_client = _make_fake_client(
            result={"name": "새이름", "category": "Job Postings!"}
        )

        with patch("sources.ai_naming.get_client", return_value=fake_client):
            autofill_source_metadata(source)

        source.refresh_from_db()
        # 규칙: 소문자화 후 [a-z_] 만 남김 -> "Job Postings!" -> "jobpostings".
        self.assertEqual(source.category, "jobpostings")
        self.assertTrue(source.ai_named)

    def test_category_sanitization_falls_back_to_etc_when_empty_after_cleaning(self) -> None:
        source = self._make_source()
        self._make_titles(source, ["채용 공고"])
        fake_client = _make_fake_client(result={"name": "새이름", "category": "123!!!"})

        with patch("sources.ai_naming.get_client", return_value=fake_client):
            autofill_source_metadata(source)

        source.refresh_from_db()
        self.assertEqual(source.category, "etc")
        self.assertTrue(source.ai_named)
