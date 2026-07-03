"""url_normalize.normalize_url 테스트 — 표기 차이 흡수(동치류) + 의미 있는 차이 보존.

DB 를 쓰지 않는 순수 함수라 SimpleTestCase 로 검증한다.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from sources.url_normalize import normalize_url


class EquivalenceCollapsesToSameKeyTests(SimpleTestCase):
    """표기만 다른 URL 은 같은 정규화 키로 모여야 한다."""

    def test_http_and_https_collapse(self) -> None:
        self.assertEqual(
            normalize_url("http://example.com/notice"),
            normalize_url("https://example.com/notice"),
        )

    def test_www_prefix_collapses_with_bare_host(self) -> None:
        self.assertEqual(
            normalize_url("https://www.example.com/notice"),
            normalize_url("https://example.com/notice"),
        )

    def test_trailing_slash_collapses_with_no_slash(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/notice/"),
            normalize_url("https://example.com/notice"),
        )

    def test_fragment_is_stripped(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/notice#section"),
            normalize_url("https://example.com/notice"),
        )

    def test_tracking_params_are_removed(self) -> None:
        tracked = (
            "https://example.com/notice"
            "?utm_source=fb&utm_medium=social&fbclid=123&gclid=abc&igshid=z"
        )
        self.assertEqual(
            normalize_url(tracked),
            normalize_url("https://example.com/notice"),
        )

    def test_ambiguous_keys_are_preserved_to_avoid_wrong_merge(self) -> None:
        # ``ref``/``source`` 는 게시판 구분자로 쓰일 수 있어 제거하지 않는다 → 서로 다른 키.
        self.assertNotEqual(
            normalize_url("https://example.com/board?ref=dept1"),
            normalize_url("https://example.com/board?ref=dept2"),
        )
        self.assertNotEqual(
            normalize_url("https://example.com/board?source=a"),
            normalize_url("https://example.com/board"),
        )

    def test_spa_hash_route_boards_stay_distinct(self) -> None:
        # 경로가 루트뿐인 해시 라우팅 SPA 는 프래그먼트로 게시판을 구분한다.
        self.assertNotEqual(
            normalize_url("https://site.com/#/board/a"),
            normalize_url("https://site.com/#/board/b"),
        )

    def test_query_param_order_does_not_matter(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/notice?b=2&a=1"),
            normalize_url("https://example.com/notice?a=1&b=2"),
        )

    def test_uppercase_host_is_lowercased(self) -> None:
        self.assertEqual(
            normalize_url("https://EXAMPLE.com/notice"),
            normalize_url("https://example.com/notice"),
        )

    def test_default_https_port_is_removed(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com:443/notice"),
            normalize_url("https://example.com/notice"),
        )

    def test_default_http_port_is_removed(self) -> None:
        self.assertEqual(
            normalize_url("http://example.com:80/notice"),
            normalize_url("https://example.com/notice"),
        )


class DistinctnessIsPreservedTests(SimpleTestCase):
    """게시판을 구분하는 의미 있는 차이는 서로 다른 키로 남아야 한다."""

    def test_different_paths_are_distinct(self) -> None:
        self.assertNotEqual(
            normalize_url("https://example.com/notice"),
            normalize_url("https://example.com/board"),
        )

    def test_meaningful_query_param_values_are_distinct(self) -> None:
        self.assertNotEqual(
            normalize_url("https://example.com/notice?menu=2"),
            normalize_url("https://example.com/notice?menu=3"),
        )

    def test_non_default_port_is_kept(self) -> None:
        self.assertNotEqual(
            normalize_url("https://example.com:8080/notice"),
            normalize_url("https://example.com/notice"),
        )

    def test_different_hosts_are_distinct(self) -> None:
        self.assertNotEqual(
            normalize_url("https://a.com/notice"),
            normalize_url("https://b.com/notice"),
        )


class RobustnessTests(SimpleTestCase):
    """빈 입력·스킴 없는 입력·파싱 불가 입력에서도 예외 없이 동작해야 한다."""

    def test_empty_string_returns_empty_string(self) -> None:
        self.assertEqual(normalize_url(""), "")

    def test_blank_string_returns_empty_string(self) -> None:
        self.assertEqual(normalize_url("   "), "")

    def test_schemeless_input_is_treated_as_https(self) -> None:
        self.assertEqual(
            normalize_url("example.com/notice"),
            "https://example.com/notice",
        )

    def test_garbage_input_does_not_raise(self) -> None:
        for garbage in ("http://[unterminated", "::::", "not a url at all ///", "https://"):
            with self.subTest(garbage=garbage):
                try:
                    normalize_url(garbage)
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"normalize_url raised {exc!r} for {garbage!r}")

    def test_root_path_slash_is_kept(self) -> None:
        self.assertEqual(normalize_url("https://example.com/"), "https://example.com/")
