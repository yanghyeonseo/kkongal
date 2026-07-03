from __future__ import annotations

import json
from typing import Optional
from unittest import mock

import httpx
from django.test import SimpleTestCase

from ai.llm import LLMClient
from crawler.generic.base import FetchResult, SourceSpec
from crawler.generic.strategies import llm_selector

# -- 픽스처: 네트워크 없이 셀렉터 적용 로직만 검증하기 위한 샘플 문서 ---------------

LIST_HTML = """<!doctype html>
<html><body>
<ul class="board-list">
  <li class="row">
    <span class="date">2026-07-01</span>
    <a class="tit" href="/notice/1">공지 1</a>
  </li>
  <li class="row">
    <span class="date">2026-07-02</span>
    <a class="tit" href="/notice/2">공지 2</a>
  </li>
</ul>
</body></html>
"""

RECIPE = {"row": "li.row", "title": "a.tit", "link": "a.tit", "date": "span.date"}


def make_fetch(pages: dict[str, tuple[str, str]]):
    """url -> (text, content_type) 매핑으로부터 네트워크 없는 fake fetch 를 만든다."""

    def fetch(url: str, *, render: Optional[str] = None, want_browser_json: bool = False) -> FetchResult:
        if url not in pages:
            return FetchResult(url=url, status=404, text="", content_type="text/plain")
        text, content_type = pages[url]
        return FetchResult(url=url, status=200, text=text, content_type=content_type, via="http")

    return fetch


class FastPathTests(SimpleTestCase):
    """학습된 레시피(spec.extraction_profile)가 있으면 LLM 호출 없이 바로 적용된다."""

    def test_applies_stored_recipe_without_llm_call(self) -> None:
        pages = {"https://example.com/board": (LIST_HTML, "text/html")}
        spec = SourceSpec(
            id="src-1", url="https://example.com/board", extraction_profile=dict(RECIPE)
        )

        with mock.patch("ai.llm.get_client") as get_client:
            outcome = llm_selector.extract(spec, make_fetch(pages))
            get_client.assert_not_called()

        self.assertEqual(outcome.kind, "llm_profile")
        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.profile, RECIPE)
        self.assertEqual(len(outcome.items), 2)
        self.assertEqual(outcome.items[0].title, "공지 1")
        self.assertEqual(str(outcome.items[0].url), "https://example.com/notice/1")
        self.assertEqual(outcome.items[0].posted_at, "2026-07-01")
        self.assertEqual(outcome.items[1].title, "공지 2")
        self.assertEqual(str(outcome.items[1].url), "https://example.com/notice/2")

    def test_stored_recipe_that_matches_nothing_returns_empty(self) -> None:
        pages = {"https://example.com/board": (LIST_HTML, "text/html")}
        bad_recipe = {"row": "li.does-not-exist", "title": "a.tit", "link": "a.tit", "date": ""}
        spec = SourceSpec(
            id="src-2", url="https://example.com/board", extraction_profile=bad_recipe
        )

        outcome = llm_selector.extract(spec, make_fetch(pages))

        self.assertEqual(outcome.kind, "llm_profile")
        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.items, [])

    def test_incomplete_stored_recipe_skips_fetch_and_llm(self) -> None:
        pages = {"https://example.com/board": (LIST_HTML, "text/html")}
        # "row" 는 있지만 title/link 가 빠져 레시피로 인정되지 않아야 한다.
        spec = SourceSpec(
            id="src-3", url="https://example.com/board", extraction_profile={"row": "li.row"}
        )

        with mock.patch("ai.llm.get_client") as get_client:
            outcome = llm_selector.extract(spec, make_fetch(pages))
            get_client.assert_not_called()

        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.items, [])


class LlmDisabledTests(SimpleTestCase):
    def test_disabled_client_returns_empty_outcome_without_fetch(self) -> None:
        spec = SourceSpec(id="src-4", url="https://example.com/board")
        fake_client = mock.Mock()
        fake_client.enabled = False

        calls: list[str] = []

        def fetch(url: str, *, render: Optional[str] = None, want_browser_json: bool = False) -> FetchResult:
            calls.append(url)
            return FetchResult(url=url, status=200, text=LIST_HTML, content_type="text/html")

        with mock.patch("ai.llm.get_client", return_value=fake_client):
            outcome = llm_selector.extract(spec, fetch)

        self.assertEqual(outcome.kind, "llm_profile")
        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.note, "llm disabled")
        self.assertEqual(calls, [])
        fake_client.complete_json.assert_not_called()


class LlmPathTests(SimpleTestCase):
    """extraction_profile 이 없을 때 LLM 에게 레시피를 물어보고 그대로 적용하는 경로."""

    def test_llm_recipe_is_applied_to_produce_items(self) -> None:
        pages = {"https://example.com/board": (LIST_HTML, "text/html")}
        spec = SourceSpec(id="src-5", url="https://example.com/board")

        fake_client = mock.Mock()
        fake_client.enabled = True
        fake_client.complete_json.return_value = dict(RECIPE)

        with mock.patch("ai.llm.get_client", return_value=fake_client):
            outcome = llm_selector.extract(spec, make_fetch(pages))

        fake_client.complete_json.assert_called_once()
        self.assertEqual(outcome.kind, "llm_profile")
        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.profile, RECIPE)
        self.assertEqual(len(outcome.items), 2)
        self.assertEqual(outcome.items[0].title, "공지 1")
        self.assertEqual(str(outcome.items[0].url), "https://example.com/notice/1")

    def test_llm_recipe_missing_required_fields_is_unusable(self) -> None:
        pages = {"https://example.com/board": (LIST_HTML, "text/html")}
        spec = SourceSpec(id="src-6", url="https://example.com/board")

        fake_client = mock.Mock()
        fake_client.enabled = True
        fake_client.complete_json.return_value = {}

        with mock.patch("ai.llm.get_client", return_value=fake_client):
            outcome = llm_selector.extract(spec, make_fetch(pages))

        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.note, "llm recipe unusable")

    def test_fetch_failure_returns_empty_outcome(self) -> None:
        spec = SourceSpec(id="src-7", url="https://example.com/board")
        fake_client = mock.Mock()
        fake_client.enabled = True

        # fetch 가 실패(404)하면 LLM 호출 전에 빈 결과로 끝나야 한다.
        with mock.patch("ai.llm.get_client", return_value=fake_client):
            outcome = llm_selector.extract(spec, make_fetch({}))  # 404 for every url

        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.note, "fetch failed")
        fake_client.complete_json.assert_not_called()


class CompleteJsonTests(SimpleTestCase):
    """ai.llm.LLMClient.complete_json 을 httpx.MockTransport 로 검증한다(ai/tests.py 패턴 참고)."""

    def test_parses_json_body_from_first_model(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps({"row": "li", "title": "a"})}}
                    ]
                },
            )

        client = LLMClient(
            api_key="test-key", min_interval=0, transport=httpx.MockTransport(handler)
        )

        result = client.complete_json([{"role": "user", "content": "hi"}])

        self.assertEqual(result, {"row": "li", "title": "a"})

    def test_total_failure_returns_empty_dict(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="server error")

        client = LLMClient(
            api_key="test-key", min_interval=0, transport=httpx.MockTransport(handler)
        )

        result = client.complete_json([{"role": "user", "content": "hi"}])

        self.assertEqual(result, {})

    def test_disabled_client_returns_empty_dict_without_request(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        client = LLMClient(
            api_key="", min_interval=0, transport=httpx.MockTransport(handler)
        )

        result = client.complete_json([{"role": "user", "content": "hi"}])

        self.assertEqual(result, {})
        self.assertEqual(calls, [])
