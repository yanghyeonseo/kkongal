from __future__ import annotations

from typing import Any, Optional

from django.test import SimpleTestCase

from crawler.generic.base import CapturedResponse, FetchResult, SourceSpec
from crawler.generic.strategies import json_api


def make_browser_fetch(captured: list[CapturedResponse], *, page_json: Any = None, page_url: str = ""):
    """browser 렌더 fetch(spec.url, render="browser", want_browser_json=True) 를 흉내낸다."""

    def fetch(url: str, *, render: Optional[str] = None, want_browser_json: bool = False) -> FetchResult:
        return FetchResult(
            url=page_url or url,
            status=200,
            text="<html></html>",
            content_type="text/html",
            via="browser",
            json=page_json,
            captured_json=captured,
        )

    return fetch


class DiscoveryTests(SimpleTestCase):
    def test_nested_list_discovery_picks_notice_like_array(self):
        """(a) 여러 배열 중 공지스러운 dict 배열을 정확히 찾고, 무관한 배열은 무시한다."""
        payload = {
            "meta": {"tags": ["news", "notice", "faq"]},
            "filters": {
                "categories": [
                    {"code": 1, "label": "General"},
                    {"code": 2, "label": "HR"},
                    {"code": 3, "label": "Sales"},
                ]
            },
            "result": {
                "data": {
                    "list": [
                        {"title": "1차 공지사항", "id": 101, "link": "/board/view.do?no=101"},
                        {"title": "2차 공지사항", "id": 102, "link": "/board/view.do?no=102"},
                    ]
                }
            },
        }
        captured = [
            CapturedResponse(
                url="https://example.com/api/board/list?page=1",
                content_type="application/json",
                json=payload,
            )
        ]
        spec = SourceSpec(id="src-1", url="https://example.com/board")
        outcome = json_api.extract(spec, make_browser_fetch(captured))

        self.assertEqual(outcome.kind, "json_api")
        self.assertTrue(outcome.applied)
        self.assertEqual(len(outcome.items), 2)
        self.assertEqual(outcome.profile["list_path"], "result.data.list")
        self.assertEqual(outcome.profile["endpoint"], "https://example.com/api/board/list?page=1")

        first = outcome.items[0]
        self.assertEqual(first.title, "1차 공지사항")
        self.assertEqual(str(first.url), "https://example.com/board/view.do?no=101")

    def test_field_mapping_picks_title_url_date(self):
        """(b) dict 키 중에서 title/url/date/summary 로 쓸 키를 best-guess 로 고른다."""
        payload = {
            "items": [
                {
                    "tit": "필드매핑 테스트 공지",
                    "link": "https://example.com/notice/9001",
                    "regDt": "2026-07-01",
                    "cn": "요약 내용",
                }
            ]
        }
        captured = [
            CapturedResponse(url="https://example.com/api/notice", content_type="application/json", json=payload)
        ]
        spec = SourceSpec(id="src-2", url="https://example.com/notice/list")
        outcome = json_api.extract(spec, make_browser_fetch(captured))

        self.assertTrue(outcome.applied)
        self.assertEqual(
            outcome.profile["fields"],
            {"title": "tit", "url": "link", "date": "regDt", "summary": "cn"},
        )
        item = outcome.items[0]
        self.assertEqual(item.title, "필드매핑 테스트 공지")
        self.assertEqual(str(item.url), "https://example.com/notice/9001")
        self.assertEqual(item.posted_at, "2026-07-01")
        self.assertEqual(item.summary, "요약 내용")

    def test_id_only_url_with_no_pattern_is_skipped(self):
        """(c) url 필드가 순수 id 뿐이고 절대 URL 을 만들 근거가 없으면 그 항목만 건너뛴다."""
        payload = {
            "list": [
                {"title": "정상 공지", "link": "/board/view.do?no=1"},
                {"title": "id만 있는 공지", "link": "555"},
            ]
        }
        captured = [
            CapturedResponse(url="https://example.com/api/board", content_type="application/json", json=payload)
        ]
        spec = SourceSpec(id="src-3", url="https://example.com/board")
        outcome = json_api.extract(spec, make_browser_fetch(captured))

        self.assertTrue(outcome.applied)
        self.assertEqual(len(outcome.items), 1)
        self.assertEqual(outcome.items[0].title, "정상 공지")
        self.assertEqual(str(outcome.items[0].url), "https://example.com/board/view.do?no=1")

    def test_no_notice_like_array_returns_empty_outcome(self):
        """(e) 어떤 배열도 공지스럽지 않으면 빈 StrategyOutcome 을 반환한다."""
        payload = {
            "status": "ok",
            "meta": {"count": 2},
            "list": [
                {"code": 1, "label": "A"},
                {"code": 2, "label": "B"},
            ],
        }
        captured = [
            CapturedResponse(url="https://example.com/api/misc", content_type="application/json", json=payload)
        ]
        spec = SourceSpec(id="src-5", url="https://example.com/misc")
        outcome = json_api.extract(spec, make_browser_fetch(captured))

        self.assertEqual(outcome.kind, "json_api")
        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.items, [])
        self.assertTrue(outcome.note)


class FastPathTests(SimpleTestCase):
    def test_fast_path_uses_stored_endpoint_list_path_and_fields(self):
        """(d) extraction_profile 에 endpoint/list_path/fields 가 있으면 discovery 를 건너뛴다."""
        endpoint = "https://example.com/api/board/list.json"
        payload = {
            "data": {
                "items": [
                    {"subject": "패스트패스 공지", "url": "https://example.com/notice/42", "postedAt": "2026-06-30"},
                ]
            }
        }
        calls: list[tuple[str, tuple, dict]] = []

        def fetch(url: str, *args, **kwargs) -> FetchResult:
            calls.append((url, args, kwargs))
            if url != endpoint:
                return FetchResult(url=url, status=404, text="")
            return FetchResult(url=url, status=200, via="http", json=payload)

        spec = SourceSpec(
            id="src-4",
            url="https://example.com/board",
            extraction_profile={
                "endpoint": endpoint,
                "list_path": "data.items",
                "fields": {"title": "subject", "url": "url", "date": "postedAt", "summary": None},
            },
        )
        outcome = json_api.extract(spec, fetch)

        self.assertTrue(outcome.applied)
        self.assertEqual(len(outcome.items), 1)
        item = outcome.items[0]
        self.assertEqual(item.title, "패스트패스 공지")
        self.assertEqual(str(item.url), "https://example.com/notice/42")
        self.assertEqual(item.posted_at, "2026-06-30")
        self.assertEqual(outcome.profile["endpoint"], endpoint)
        self.assertEqual(outcome.profile["list_path"], "data.items")
        # fast-path 는 학습된 endpoint 만 fetch 해야 한다(discovery 인자로 spec.url 을 건드리면 안 됨).
        self.assertEqual(calls, [(endpoint, (), {})])
