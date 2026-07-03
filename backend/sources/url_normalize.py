"""URL 정규화 — 같은 공지 게시판이 표기 차이로 다른 소스로 갈라지는 것을 막는다.

사용자마다 붙여넣는 URL 은 조금씩 다르다(스킴, www, 끝 슬래시, utm 추적 파라미터,
프래그먼트, 쿼리 순서 등). 이들을 하나의 **정규화 키**로 모으면:

- 같은 게시판이 하나의 NoticeSource 로 합쳐지고,
- 먼저 학습된 크롤 레시피(extraction_profile)를 다음 구독자가 그대로 재사용해
  사용자가 늘수록 자연히 스케일된다.

보수적으로 정규화한다 — 게시판을 구분하는 의미 있는 쿼리(menu, board id 등)는 남기고,
추적/표시용 파라미터만 제거한다. 원본 URL(fetch 대상)은 NoticeSource.url 에 따로 보존한다.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 명백한 광고/애널리틱스 클릭 식별자만 제거한다(제거해도 같은 페이지가 확실한 것들).
# ``source``·``ref``·``spm`` 같은 평문 키는 게시판 구분자로 쓰이는 경우가 있어 일부러 뺐다
# — 잘못 병합해 서로 다른 게시판의 공지가 섞이는 편이, 중복 소스가 하나 더 생기는 것보다 나쁘다.
_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "gclsrc",
    "msclkid",
    "igshid",
    "yclid",
    "_ga",
    "mc_cid",
    "mc_eid",
}
_TRACKING_PREFIXES = ("utm_",)


def _is_tracking(key: str) -> bool:
    low = key.lower()
    return low in _TRACKING_KEYS or low.startswith(_TRACKING_PREFIXES)


def normalize_url(url: str) -> str:
    """URL 을 정규화 키로 변환한다. 파싱 불가하면 입력을 그대로(strip) 돌려준다.

    규칙:
      - 스킴 → https 로 통일(http/https 는 같은 사이트로 본다). 스킴이 없으면 https 를 붙인다.
      - 호스트 → 소문자, 선행 ``www.`` 제거, 기본 포트(80/443) 제거.
      - 경로 → 끝 슬래시 제거(루트 ``/`` 는 유지).
      - 쿼리 → 추적 파라미터 제거 후 key 로 정렬(순서 차이 흡수). 남는 게 없으면 제거.
      - 프래그먼트(#...) → 제거. 단 경로가 루트("/")뿐이면 SPA 해시 라우팅
        (예: ``site.com/#/board/a``)일 수 있어 프래그먼트를 살려 게시판을 구분한다.
    """
    if not url:
        return ""
    raw = url.strip()
    if not raw:
        return ""

    # 스킴이 없으면 https 를 붙여 파싱이 host 를 netloc 으로 인식하게 한다.
    if "://" not in raw:
        raw = "https://" + raw

    try:
        parts = urlsplit(raw)
    except ValueError:
        return url.strip()

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return url.strip()

    # 기본 포트는 버리고, 비표준 포트만 남긴다.
    port = parts.port
    if port and port not in (80, 443):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if not _is_tracking(key)
    ]
    kept.sort()
    query = urlencode(kept)

    # 해시 라우팅 SPA(경로가 "/" 뿐)만 프래그먼트를 dedup 키에 남긴다.
    fragment = parts.fragment if path == "/" else ""

    return urlunsplit(("https", netloc, path, query, fragment))
