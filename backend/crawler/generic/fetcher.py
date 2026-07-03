"""fetch 계단(insane-search Phase 1→3 차용).

한 URL 을 가져올 때 비용이 싼 순서로 승격한다:

  1. http        : httpx (가장 쌈, 대부분의 사이트)
  2. impersonate : curl_cffi 로 실제 브라우저 TLS 지문 위장(403/기본 WAF 우회)
  3. browser     : Playwright headless(JS 렌더 + 사이트 내부 JSON API 수집)

``render`` 를 지정하면 그 백엔드로 바로 간다(학습된 소스의 재크롤 비용 절감). 미지정이면
차단 신호(blocked)나 빈 응답일 때만 다음 단계로 올라간다. curl_cffi/playwright 는 지연
import 하므로 미설치여도 모듈 import 는 실패하지 않고 해당 단계만 건너뛴다.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

from ..config_loader import Defaults
from .base import CapturedResponse, FetchResult

log = logging.getLogger("crawler.generic.fetch")


def _url_is_public(url: str) -> bool:
    """SSRF 방어: 호스트가 공인 IP 로만 해석되는지 확인한다.

    generic 파이프라인은 사용자가 등록한 임의 URL 을 서버가 직접 가져온다. 가드가 없으면
    누구든 ``http://169.254.169.254/...``(클라우드 메타데이터)나 ``http://localhost:6379/``
    같은 내부 자원을 서버로 대신 요청시켜 응답을 inbox 로 빼돌릴 수 있다. 그래서 fetch 직전
    (그리고 리다이렉트 최종 URL)에 대해 호스트의 모든 해석 IP 가 사설/루프백/링크로컬/예약
    대역이 아닌지 검사한다. http/https 스킴만 허용한다.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
    return True

# 응답 본문에 있으면 anti-bot 차단 페이지로 보는 마커들(대소문자 무시).
_BLOCK_MARKERS = (
    "just a moment",              # Cloudflare challenge
    "attention required! | cloudflare",
    "cf-browser-verification",
    "_cf_chl",
    "checking your browser",
    "access denied",              # Akamai
    "px-captcha",                 # PerimeterX
    "datadome",                   # DataDome
    "please enable javascript and cookies",
)
_BLOCK_STATUSES = {401, 403, 406, 429, 503}
# curl_cffi 로 위장할 브라우저 프로필(insane-search: safari → chrome → firefox 순).
_IMPERSONATE_PROFILES = ("safari", "chrome", "firefox")
# browser 단계에서 수집할 XHR JSON 한 건당 최대 바이트(폭주 방지).
_MAX_CAPTURED_BYTES = 2_000_000


def _looks_blocked(status: int, text: str) -> bool:
    if status in _BLOCK_STATUSES:
        return True
    head = text[:4000].lower()
    return any(marker in head for marker in _BLOCK_MARKERS)


def _is_json_ct(content_type: str) -> bool:
    ct = content_type.lower()
    return "json" in ct or ct.endswith("+json")


class Escalator:
    """계단식 fetch 실행기. 한 크롤 동안 재사용하며, 필요 시 browser 를 한 번만 띄운다."""

    def __init__(self, defaults: Defaults) -> None:
        self.defaults = defaults

    # -- public ---------------------------------------------------------------
    def fetch(
        self,
        url: str,
        *,
        render: Optional[str] = None,
        want_browser_json: bool = False,
    ) -> FetchResult:
        """URL 을 가져온다. render 지정 시 그 백엔드만, 미지정 시 자동 승격.

        want_browser_json=True 면 browser 단계에서 사이트 내부 JSON API 응답을 함께 수집한다.
        """
        # SSRF 가드: 내부/사설 대역으로 해석되는 호스트는 어떤 tier 도 시도하지 않는다.
        if not _url_is_public(url):
            log.warning("blocked non-public fetch target: %s", url)
            return FetchResult(url=url, status=0, blocked=True, error="non-public host blocked")

        if render in ("http", "impersonate", "browser"):
            ladder = [render]
        else:
            ladder = ["http", "impersonate", "browser"]

        last: Optional[FetchResult] = None
        for tier in ladder:
            result = self._fetch_one(url, tier, want_browser_json=want_browser_json)
            # 리다이렉트가 내부 자원으로 튀었을 수 있다 → 최종 URL 도 공인인지 재확인.
            if result.url != url and not _url_is_public(result.url):
                log.warning("fetch redirected to non-public host: %s → %s", url, result.url)
                last = FetchResult(url=result.url, status=0, blocked=True, error="redirected to non-public host")
                continue
            if result.ok:
                return result
            last = result
            # 차단/빈 응답이면 다음 단계로. auth 경계는 더 올라가도 못 뚫으니 멈춘다.
            if result.auth_required:
                break
        return last or FetchResult(url=url, status=0, error="no fetch tier available")

    # -- tiers ----------------------------------------------------------------
    def _fetch_one(self, url: str, tier: str, *, want_browser_json: bool) -> FetchResult:
        try:
            if tier == "http":
                return self._fetch_http(url)
            if tier == "impersonate":
                return self._fetch_impersonate(url)
            if tier == "browser":
                return self._fetch_browser(url, want_browser_json=want_browser_json)
        except Exception as exc:  # noqa: BLE001 - 한 단계 실패가 계단 전체를 죽이지 않게.
            log.debug("fetch tier %s failed for %s: %r", tier, url, exc)
            return FetchResult(url=url, status=0, via=tier, error=repr(exc))
        return FetchResult(url=url, status=0, via=tier, error=f"unknown tier {tier}")

    def _fetch_http(self, url: str) -> FetchResult:
        import httpx

        headers = {
            "User-Agent": self.defaults.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        with httpx.Client(
            headers=headers,
            timeout=self.defaults.request_timeout_seconds,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            resp = client.get(url)
        return self._build_result(
            url=str(resp.url),
            status=resp.status_code,
            text=resp.text,
            content_type=resp.headers.get("content-type", ""),
            via="http",
        )

    def _fetch_impersonate(self, url: str) -> FetchResult:
        from curl_cffi import requests as cffi  # 지연 import

        last: Optional[FetchResult] = None
        for profile in _IMPERSONATE_PROFILES:
            resp = cffi.get(
                url,
                impersonate=profile,
                timeout=self.defaults.request_timeout_seconds,
                allow_redirects=True,
            )
            result = self._build_result(
                url=str(resp.url),
                status=resp.status_code,
                text=resp.text,
                content_type=resp.headers.get("content-type", ""),
                via="impersonate",
            )
            if result.ok:
                return result
            last = result
        return last or FetchResult(url=url, status=0, via="impersonate", error="impersonate failed")

    def _fetch_browser(self, url: str, *, want_browser_json: bool) -> FetchResult:
        from playwright.sync_api import sync_playwright  # 지연 import

        captured: list[CapturedResponse] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=self.defaults.user_agent,
                    locale="ko-KR",
                )
                page = context.new_page()

                if want_browser_json:
                    page.on("response", lambda resp: self._maybe_capture(resp, captured))

                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.defaults.request_timeout_seconds * 1000,
                )
                # 클라이언트 렌더 목록이 채워질 시간을 잠깐 준다(networkidle 은 과도할 수 있어 폴백).
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:  # noqa: BLE001
                    pass

                html = page.content()
                status = response.status if response else 200
                content_type = ""
                if response:
                    content_type = response.headers.get("content-type", "")
                return self._build_result(
                    url=page.url,
                    status=status,
                    text=html,
                    content_type=content_type or "text/html",
                    via="browser",
                    captured_json=captured,
                )
            finally:
                browser.close()

    def _maybe_capture(self, resp, captured: list[CapturedResponse]) -> None:
        """browser 렌더 중 JSON 응답을 사이트 내부 API 후보로 수집한다(best-effort)."""
        try:
            content_type = resp.headers.get("content-type", "")
            if not _is_json_ct(content_type):
                return
            body = resp.body()
            if not body or len(body) > _MAX_CAPTURED_BYTES:
                return
            import json as _json

            captured.append(
                CapturedResponse(
                    url=resp.url,
                    content_type=content_type,
                    json=_json.loads(body.decode("utf-8", "replace")),
                )
            )
        except Exception:  # noqa: BLE001 - 수집 실패는 조용히 넘긴다.
            return

    # -- shared ---------------------------------------------------------------
    def _build_result(
        self,
        *,
        url: str,
        status: int,
        text: str,
        content_type: str,
        via: str,
        captured_json: Optional[list[CapturedResponse]] = None,
    ) -> FetchResult:
        json_payload = None
        if _is_json_ct(content_type) and text:
            try:
                import json as _json

                json_payload = _json.loads(text)
            except Exception:  # noqa: BLE001
                json_payload = None
        return FetchResult(
            url=url,
            status=status,
            text=text or "",
            content_type=content_type,
            via=via,
            json=json_payload,
            captured_json=captured_json or [],
            blocked=_looks_blocked(status, text or ""),
        )
