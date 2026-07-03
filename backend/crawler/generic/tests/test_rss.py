from __future__ import annotations

from typing import Optional

from django.test import SimpleTestCase

from crawler.generic.base import FetchResult, SourceSpec
from crawler.generic.strategies import rss

# -- 픽스처: 네트워크 없이 파싱 로직만 검증하기 위한 샘플 문서들 -----------------

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example RSS</title>
    <link>https://example.com</link>
    <description>example</description>
    <item>
      <title>공지 1</title>
      <link>https://example.com/notice/1</link>
      <pubDate>Mon, 01 Jul 2026 09:00:00 +0900</pubDate>
      <description>첫 번째 공지 요약</description>
    </item>
    <item>
      <title>공지 2</title>
      <link>https://example.com/notice/2</link>
      <pubDate>Tue, 02 Jul 2026 09:00:00 +0900</pubDate>
      <description>두 번째 공지 요약</description>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <link href="https://example.org/"/>
  <updated>2026-07-01T09:00:00Z</updated>
  <entry>
    <title>공지 A</title>
    <link href="https://example.org/notice/a"/>
    <id>https://example.org/notice/a</id>
    <updated>2026-07-01T09:00:00Z</updated>
    <summary>공지 A 요약</summary>
  </entry>
  <entry>
    <title>공지 B</title>
    <link href="https://example.org/notice/b"/>
    <id>https://example.org/notice/b</id>
    <updated>2026-07-02T09:00:00Z</updated>
    <summary>공지 B 요약</summary>
  </entry>
</feed>
"""

HTML_WITH_LINK_TAG = """<!doctype html>
<html>
<head>
  <title>Example site</title>
  <link rel="alternate" type="application/rss+xml" title="RSS" href="/custom/feed.xml">
</head>
<body><p>hello</p></body>
</html>
"""

HTML_NO_FEED_HINT = """<!doctype html>
<html>
<head><title>No feed here</title></head>
<body><p>nothing</p></body>
</html>
"""

HTML_PLAIN = """<!doctype html>
<html><head><title>plain</title></head><body>plain page</body></html>
"""


def make_fetch(pages: dict[str, tuple[str, str]]):
    """url -> (text, content_type) 매핑으로부터 네트워크 없는 fake fetch 를 만든다."""

    def fetch(url: str, *, render: Optional[str] = None, want_browser_json: bool = False) -> FetchResult:
        if url not in pages:
            return FetchResult(url=url, status=404, text="", content_type="text/plain")
        text, content_type = pages[url]
        return FetchResult(url=url, status=200, text=text, content_type=content_type, via="http")

    return fetch


class RssStrategyTests(SimpleTestCase):
    def test_discovery_via_link_alternate(self):
        """(a) HTML <link rel=alternate> 로 피드를 찾는 경로."""
        pages = {
            "https://example.com/": (HTML_WITH_LINK_TAG, "text/html"),
            "https://example.com/custom/feed.xml": (RSS_SAMPLE, "application/rss+xml"),
        }
        spec = SourceSpec(id="src-1", url="https://example.com/")
        outcome = rss.extract(spec, make_fetch(pages))

        self.assertEqual(outcome.kind, "rss")
        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.profile, {"feed": "https://example.com/custom/feed.xml"})
        self.assertEqual(len(outcome.items), 2)
        self.assertEqual(outcome.items[0].title, "공지 1")
        self.assertEqual(str(outcome.items[0].url), "https://example.com/notice/1")
        self.assertTrue(outcome.items[0].posted_at)

    def test_common_path_fallback(self):
        """(b) <link> 힌트가 없을 때 흔한 경로(/rss 등)를 순서대로 시도하는 경로."""
        pages = {
            "https://example.com/": (HTML_NO_FEED_HINT, "text/html"),
            "https://example.com/rss": (RSS_SAMPLE, "application/rss+xml"),
        }
        spec = SourceSpec(id="src-2", url="https://example.com/")
        outcome = rss.extract(spec, make_fetch(pages))

        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.profile, {"feed": "https://example.com/rss"})
        self.assertEqual(len(outcome.items), 2)

    def test_fast_path_uses_learned_feed(self):
        """(c) extraction_profile["feed"] 가 있으면 discovery 를 건너뛰는 fast-path."""
        calls: list[str] = []
        pages = {
            "https://example.org/feeds/atom.xml": (ATOM_SAMPLE, "application/atom+xml"),
        }

        def fetch(url: str, *, render: Optional[str] = None, want_browser_json: bool = False) -> FetchResult:
            calls.append(url)
            if url not in pages:
                return FetchResult(url=url, status=404, text="")
            text, content_type = pages[url]
            return FetchResult(url=url, status=200, text=text, content_type=content_type, via="http")

        spec = SourceSpec(
            id="src-3",
            url="https://example.org/",
            extraction_profile={"feed": "https://example.org/feeds/atom.xml"},
        )
        outcome = rss.extract(spec, fetch)

        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.profile, {"feed": "https://example.org/feeds/atom.xml"})
        # fast-path 는 학습된 피드만 fetch 해야 한다(spec.url discovery 를 건드리면 안 됨).
        self.assertEqual(calls, ["https://example.org/feeds/atom.xml"])

    def test_rss_and_atom_samples_parse_into_items(self):
        """(d) 실제 RSS 2.0/Atom 샘플이 title/url/posted_at 을 채운 items 로 파싱되는지."""
        rss_pages = {"https://rss.example.com/feed.xml": (RSS_SAMPLE, "application/rss+xml")}
        spec = SourceSpec(
            id="src-rss",
            url="https://rss.example.com/",
            extraction_profile={"feed": "https://rss.example.com/feed.xml"},
        )
        outcome = rss.extract(spec, make_fetch(rss_pages))
        self.assertEqual(outcome.kind, "rss")
        self.assertEqual(len(outcome.items), 2)
        for item in outcome.items:
            self.assertTrue(item.title)
            self.assertTrue(str(item.url))
            self.assertTrue(item.posted_at)

        atom_pages = {"https://atom.example.com/feed.xml": (ATOM_SAMPLE, "application/atom+xml")}
        spec2 = SourceSpec(
            id="src-atom",
            url="https://atom.example.com/",
            extraction_profile={"feed": "https://atom.example.com/feed.xml"},
        )
        outcome2 = rss.extract(spec2, make_fetch(atom_pages))
        self.assertEqual(len(outcome2.items), 2)
        for item in outcome2.items:
            self.assertTrue(item.title)
            self.assertTrue(str(item.url))
            self.assertTrue(item.posted_at)

    def test_no_feed_returns_empty_outcome(self):
        """(e) 어디에서도 피드를 못 찾으면 빈 StrategyOutcome 을 반환."""
        pages = {
            "https://nofeed.example.com/": (HTML_PLAIN, "text/html"),
        }
        spec = SourceSpec(id="src-4", url="https://nofeed.example.com/")
        outcome = rss.extract(spec, make_fetch(pages))

        self.assertEqual(outcome.kind, "rss")
        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.items, [])
        self.assertEqual(outcome.note, "no feed")
