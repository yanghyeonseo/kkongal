from __future__ import annotations

from django.test import SimpleTestCase

from ..base import FetchResult, SourceSpec
from ..strategies.heuristic import extract

BASE_URL = "https://example.com/board/list"

TABLE_HTML = """
<html><body>
<table>
  <thead><tr><th>번호</th><th>제목</th><th>날짜</th></tr></thead>
  <tbody>
    <tr><td>4</td><td><a href="/notice/1">공지 하나</a></td><td>2026.07.01</td></tr>
    <tr><td>3</td><td><a href="/notice/2">공지 둘</a></td><td>2026.07.02</td></tr>
    <tr><td>2</td><td><a href="/notice/3">공지 셋</a></td><td>2026.07.03</td></tr>
    <tr><td>1</td><td><a href="/notice/4">공지 넷</a></td><td>2026.07.04</td></tr>
  </tbody>
</table>
</body></html>
"""

UL_HTML = """
<html><body>
<div class="board-wrap">
  <ul class="board-list">
    <li><a href="/card/1">카드 공지 하나</a><span>2026.07.01</span></li>
    <li><a href="/card/2">카드 공지 둘</a><span>2026.07.02</span></li>
    <li><a href="/card/3">카드 공지 셋</a><span>2026.07.03</span></li>
  </ul>
</div>
</body></html>
"""

NAV_ONLY_HTML = """
<html><body>
<nav>
  <ul class="menu">
    <li><a href="/">Home</a></li>
    <li><a href="/about">About</a></li>
    <li><a href="javascript:void(0)">Login</a></li>
    <li><a href="#">Search</a></li>
  </ul>
</nav>
<footer><a href="/terms">Terms</a> <a href="/privacy">Privacy</a></footer>
</body></html>
"""


def _fake_fetch(html: str, url: str = BASE_URL):
    def fetch(target_url: str, **kwargs):
        return FetchResult(url=url, status=200, text=html, content_type="text/html", via="http")

    return fetch


class ExtractDiscoveryTests(SimpleTestCase):
    def test_table_rows_are_discovered(self):
        spec = SourceSpec(id="src-1", url=BASE_URL)
        outcome = extract(spec, _fake_fetch(TABLE_HTML))

        self.assertEqual(outcome.kind, "heuristic")
        self.assertTrue(outcome.applied)
        self.assertEqual(len(outcome.items), 4)
        self.assertEqual(outcome.profile, {"row": "table tbody tr"})

        first = outcome.items[0]
        self.assertEqual(first.title, "공지 하나")
        self.assertEqual(str(first.url), "https://example.com/notice/1")
        self.assertEqual(first.posted_at, "2026.07.01")

        last = outcome.items[-1]
        self.assertEqual(last.title, "공지 넷")
        self.assertEqual(str(last.url), "https://example.com/notice/4")
        self.assertEqual(last.posted_at, "2026.07.04")

    def test_ul_li_card_list_is_discovered(self):
        spec = SourceSpec(id="src-2", url=BASE_URL)
        outcome = extract(spec, _fake_fetch(UL_HTML))

        self.assertTrue(outcome.applied)
        self.assertEqual(len(outcome.items), 3)
        self.assertEqual(outcome.profile, {"row": "ul.board-list li"})

        titles = [item.title for item in outcome.items]
        urls = [str(item.url) for item in outcome.items]
        dates = [item.posted_at for item in outcome.items]

        self.assertEqual(titles, ["카드 공지 하나", "카드 공지 둘", "카드 공지 셋"])
        self.assertEqual(
            urls,
            [
                "https://example.com/card/1",
                "https://example.com/card/2",
                "https://example.com/card/3",
            ],
        )
        self.assertEqual(dates, ["2026.07.01", "2026.07.02", "2026.07.03"])

    def test_nav_menu_is_not_mistaken_for_a_list(self):
        spec = SourceSpec(id="src-3", url=BASE_URL)
        outcome = extract(spec, _fake_fetch(NAV_ONLY_HTML))

        self.assertEqual(outcome.kind, "heuristic")
        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.items, [])

    def test_fast_path_uses_stored_row_selector(self):
        spec = SourceSpec(
            id="src-4",
            url=BASE_URL,
            extraction_profile={"row": "table tbody tr"},
        )
        outcome = extract(spec, _fake_fetch(TABLE_HTML))

        self.assertTrue(outcome.applied)
        self.assertEqual(len(outcome.items), 4)
        self.assertEqual(outcome.profile, {"row": "table tbody tr"})
        self.assertIn("fast-path", outcome.note)

    def test_no_ok_fetch_result_returns_empty(self):
        spec = SourceSpec(id="src-5", url=BASE_URL)

        def fetch(target_url: str, **kwargs):
            return FetchResult(url=BASE_URL, status=500, text="", via="http")

        outcome = extract(spec, fetch)

        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.items, [])

    def test_fetch_exception_is_swallowed(self):
        spec = SourceSpec(id="src-6", url=BASE_URL)

        def fetch(target_url: str, **kwargs):
            raise RuntimeError("network is down")

        outcome = extract(spec, fetch)

        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.items, [])
