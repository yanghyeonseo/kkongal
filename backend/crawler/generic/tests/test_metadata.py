"""metadata 하이드레이션 모듈 단위테스트 — 네트워크 없음.

``fetch`` 는 url -> FetchResult 매핑을 흉내내는 가짜 함수로 주입한다. 실제 HTTP/
브라우저 호출은 일절 하지 않는다.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from crawler.generic.base import FetchResult
from crawler.generic.metadata import (
    article_fields_from_jsonld,
    extract_jsonld,
    extract_ogp,
    hydrate,
)
from crawler.schemas import RawNotice

# -- fixtures ------------------------------------------------------------------

OGP_JSONLD_HTML = """
<html><head>
<meta property="og:title" content="OGP 제목">
<meta property="og:description" content="OGP 설명입니다">
<meta property="og:article:published_time" content="2026-07-01T09:00:00+09:00">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"NewsArticle","headline":"기사 제목",
 "articleBody":"이것은 JSON-LD 기사 본문입니다.","datePublished":"2026-07-01T09:00:00+09:00"}
</script>
</head><body><article>대체용 본문(article 셀렉터)</article></body></html>
"""

GRAPH_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebPage","name":"페이지"},
  {"@type":"NewsArticle","headline":"그래프 기사","articleBody":"그래프 본문 내용입니다.",
   "datePublished":"2026-07-02T10:00:00+09:00"}
]}
</script>
</head><body></body></html>
"""

OG_DESC_ONLY_HTML = """
<html><head>
<meta property="og:description" content="OG 설명 폴백입니다">
</head><body><p>셀렉터에 안 걸리는 본문</p></body></html>
"""

GARBAGE_HTML = "<<< not even close to html %%% \x00\x01"


def _fetch_from(mapping: dict[str, FetchResult]):
    def fetch(url, **kwargs):
        return mapping.get(url, FetchResult(url=url, status=404, text="", error="not found in fixture"))
    return fetch


def _notice(idx: int, **overrides) -> RawNotice:
    fields = {
        "source_id": "test-src",
        "title": f"공지 {idx}",
        "url": f"https://example.com/notice/{idx}",
    }
    fields.update(overrides)
    return RawNotice(**fields)


# -- extract_ogp -----------------------------------------------------------------


class ExtractOgpTests(SimpleTestCase):
    def test_pulls_title_description_and_published_time(self):
        ogp = extract_ogp(OGP_JSONLD_HTML)
        self.assertEqual(ogp["title"], "OGP 제목")
        self.assertEqual(ogp["description"], "OGP 설명입니다")
        self.assertEqual(ogp["article:published_time"], "2026-07-01T09:00:00+09:00")

    def test_empty_or_broken_html_returns_empty_dict(self):
        self.assertEqual(extract_ogp(""), {})
        self.assertEqual(extract_ogp(GARBAGE_HTML), {})


# -- extract_jsonld / article_fields_from_jsonld ----------------------------------


class ExtractJsonldTests(SimpleTestCase):
    def test_parses_newsarticle_block(self):
        blocks = extract_jsonld(OGP_JSONLD_HTML)
        self.assertEqual(len(blocks), 1)
        fields = article_fields_from_jsonld(blocks)
        self.assertEqual(fields["articleBody"], "이것은 JSON-LD 기사 본문입니다.")
        self.assertEqual(fields["datePublished"], "2026-07-01T09:00:00+09:00")
        self.assertEqual(fields["headline"], "기사 제목")

    def test_parses_graph_wrapper_and_prefers_article_type(self):
        blocks = extract_jsonld(GRAPH_HTML)
        # WebPage + NewsArticle 두 블록이 평탄화되어 나와야 한다.
        self.assertEqual(len(blocks), 2)
        fields = article_fields_from_jsonld(blocks)
        # WebPage 가 먼저 나오더라도 NewsArticle(기사 타입)이 우선되어야 한다.
        self.assertEqual(fields["articleBody"], "그래프 본문 내용입니다.")
        self.assertEqual(fields["datePublished"], "2026-07-02T10:00:00+09:00")

    def test_garbage_html_returns_empty_list(self):
        self.assertEqual(extract_jsonld(GARBAGE_HTML), [])
        self.assertEqual(extract_jsonld(""), [])


# -- hydrate -----------------------------------------------------------------------


class HydrateTests(SimpleTestCase):
    def test_fills_body_from_jsonld_article_body(self):
        item = _notice(1)
        fetch = _fetch_from({str(item.url): FetchResult(url=str(item.url), status=200, text=OGP_JSONLD_HTML)})
        hydrate([item], fetch)
        self.assertEqual(item.body, "이것은 JSON-LD 기사 본문입니다.")

    def test_fills_summary_from_og_description(self):
        item = _notice(2)
        fetch = _fetch_from({str(item.url): FetchResult(url=str(item.url), status=200, text=OG_DESC_ONLY_HTML)})
        hydrate([item], fetch)
        self.assertEqual(item.summary, "OG 설명 폴백입니다")

    def test_fills_posted_at_from_article_published_time(self):
        item = _notice(3)
        fetch = _fetch_from({str(item.url): FetchResult(url=str(item.url), status=200, text=OGP_JSONLD_HTML)})
        hydrate([item], fetch)
        self.assertEqual(item.posted_at, "2026-07-01T09:00:00+09:00")

    def test_does_not_overwrite_preset_fields(self):
        item = _notice(
            4,
            body="이미 있는 본문",
            summary="이미 있는 요약",
            posted_at="2020-01-01",
        )
        fetch = _fetch_from({str(item.url): FetchResult(url=str(item.url), status=200, text=OGP_JSONLD_HTML)})
        hydrate([item], fetch)
        self.assertEqual(item.body, "이미 있는 본문")
        self.assertEqual(item.summary, "이미 있는 요약")
        self.assertEqual(item.posted_at, "2020-01-01")

    def test_respects_cap_leaving_extra_items_untouched(self):
        items = [_notice(i) for i in range(3)]
        mapping = {
            str(item.url): FetchResult(url=str(item.url), status=200, text=OGP_JSONLD_HTML)
            for item in items
        }
        hydrate(items, _fetch_from(mapping), cap=2)
        self.assertIsNotNone(items[0].body)
        self.assertIsNotNone(items[1].body)
        # cap 을 넘긴 세 번째 항목은 손대지 않아야 한다.
        self.assertIsNone(items[2].body)
        self.assertIsNone(items[2].summary)
        self.assertIsNone(items[2].posted_at)

    def test_item_with_garbage_or_failed_fetch_is_skipped_without_error(self):
        ok_item = _notice(5)
        bad_item = _notice(6)
        mapping = {
            str(ok_item.url): FetchResult(url=str(ok_item.url), status=200, text=OGP_JSONLD_HTML),
            str(bad_item.url): FetchResult(url=str(bad_item.url), status=500, text=GARBAGE_HTML, error="boom"),
        }
        result = hydrate([ok_item, bad_item], _fetch_from(mapping))
        self.assertEqual(result, [ok_item, bad_item])
        self.assertIsNotNone(ok_item.body)
        self.assertIsNone(bad_item.body)
        self.assertIsNone(bad_item.summary)
        self.assertIsNone(bad_item.posted_at)

    def test_returns_same_list_object(self):
        items = [_notice(7)]
        fetch = _fetch_from({})
        result = hydrate(items, fetch)
        self.assertIs(result, items)
