from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse
from typing import Iterable

import httpx

from ..config_loader import Defaults, SiteConfig
from ..schemas import RawNotice
from .base import ScrapeContext, extract_body_text, extract_meta_content, first_text, make_notice, safe_href, take

NOISE_RE = re.compile(r"\s*(관심기업 등록|스크랩|지원자격|\b대기업\b|\b외국계\b)\s*")
NON_WORD_RE = re.compile(r"[^0-9A-Za-z가-힣]+")
BODY_SELECTORS = ["#content", ".wrap_jview", ".recruit_template"]
DETAIL_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.saramin.co.kr/zf_user/jobs/hot100",
}


def _clean_label(text: str) -> str:
    cleaned = NOISE_RE.sub(" ", text or "")
    return " ".join(cleaned.split()).strip("[] ")


def _cmp_key(text: str) -> str:
    base = text.replace("(주)", "").replace("㈜", "")
    return NON_WORD_RE.sub("", base).lower()


def _strip_company_prefix(title: str, company: str) -> str:
    raw = title.strip()
    key = _cmp_key(company)
    if not raw or not key:
        return raw
    bracketed = re.match(r"^\[([^\]]+)\]\s*(.*)$", raw)
    if bracketed and _cmp_key(bracketed.group(1)) == key:
        return bracketed.group(2).strip()
    plain = re.match(r"^([^\]\s]+)\]?\s*(.*)$", raw)
    if plain and _cmp_key(plain.group(1)) == key:
        return plain.group(2).strip()
    return raw


def _strip_orphan_bracket_prefix(title: str) -> str:
    return re.sub(r"^[^\[\]]+\]\s*", "", title.strip())


def _normalized_detail_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path == "/zf_user/jobs/relay/view":
        rec_idx = (parse_qs(parsed.query).get("rec_idx") or [""])[0]
        if rec_idx:
            return f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}"
    return url


def parse_html(html: str, site: SiteConfig, defaults: Defaults) -> list[RawNotice]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    items = (
        soup.select(".list_item, .item_recruit, .list_body .item, .common_recruilt_list li")
        or soup.select("li:has(a[href*='/zf_user/jobs'])")
    )
    out: list[RawNotice] = []
    for item in items:
        link = item.select_one(
            "a[href*='/zf_user/jobs'], a[href*='rec_idx'], a[href]"
        )
        if not link:
            continue
        url = safe_href(link.get("href", ""), site.url)
        if not url:
            continue
        title = (
            first_text(item.select_one(".job_tit span, .job_tit strong, .title, h2, .area_job .job_tit"))
            or first_text(link)
        )
        company = first_text(item.select_one(".company_nm, .corp_name, .area_corp"))
        title = _clean_label(title)
        company = _clean_label(company)
        if company:
            title = _strip_company_prefix(title, company)
        title = _strip_orphan_bracket_prefix(title)
        # HOT100 목록엔 절대 게시일이 없고 ".deadlines" 에 상대표현("6일 전 등록")이 있다.
        # (".date" 는 마감일 D-N/~MM.DD 라 게시일이 아니다.) 상대표현은
        # repository.parse_notice_datetime 이 절대 시각으로 환산한다.
        posted_at = first_text(item.select_one(".support_detail .deadlines")) or None
        notice = make_notice(
            site_id=site.id,
            title=f"[{company}] {title}" if company else title,
            url=url,
            posted_at=posted_at,
            summary=company or None,
        )
        if notice:
            out.append(notice)
    return take(out, defaults.max_items_per_run)


def scrape(ctx: ScrapeContext) -> Iterable[RawNotice]:
    resp = ctx.client.get(ctx.site.url)
    resp.raise_for_status()
    items = parse_html(resp.text, ctx.site, ctx.defaults)
    for item in items:
        try:
            detail = ctx.client.get(
                _normalized_detail_url(str(item.url)),
                headers=DETAIL_HEADERS,
                timeout=8,
            )
            detail.raise_for_status()
            item.body = (
                extract_body_text(detail.text, BODY_SELECTORS)
                or extract_meta_content(detail.text, ["description", "og:description"])
            )
        except httpx.HTTPError:
            item.body = item.summary
    return items
