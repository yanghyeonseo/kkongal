from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..schemas import RawNotice
from .base import ScrapeContext, compact_text, make_notice, take

SUPABASE_URL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.supabase\.co")
SUPABASE_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-.]{80,}")


@dataclass(frozen=True)
class SupabaseCredentials:
    url: str
    anon_key: str


@dataclass(frozen=True)
class TheDreamFeed:
    table: str
    order: str
    mapper: Callable[[str, dict[str, Any]], RawNotice | None]
    type_filter: str | None = None


_CREDENTIAL_CACHE: dict[str, SupabaseCredentials] = {}


def scrape_thedream_feed(ctx: ScrapeContext, feed: TheDreamFeed) -> Iterable[RawNotice]:
    credentials = _supabase_credentials(ctx)
    endpoint = f"{credentials.url}/rest/v1/{feed.table}"
    params = {
        "select": "*",
        "order": feed.order,
        "limit": str(ctx.defaults.max_items_per_run),
    }
    if feed.type_filter:
        params["type"] = f"eq.{feed.type_filter}"

    resp = ctx.client.get(
        endpoint,
        params=params,
        headers={
            "Accept": "application/json",
            "apikey": credentials.anon_key,
            "Authorization": f"Bearer {credentials.anon_key}",
        },
    )
    resp.raise_for_status()

    rows = resp.json()
    notices = [feed.mapper(ctx.site.id, row) for row in rows]
    return take((notice for notice in notices if notice), ctx.defaults.max_items_per_run)


def make_scholarship_notice(site_id: str, row: dict[str, Any]) -> RawNotice | None:
    title = _first(row, "name", "group_name")
    notice = make_notice(
        site_id=site_id,
        title=title,
        url=_detail_url("scholarships", row.get("id")),
        posted_at=_first(row, "created_at", "application_start", "application_end") or None,
        summary=_summary(
            row,
            ("foundation", "주관"),
            ("category", "분류"),
            ("amount", "지원금"),
            ("application_period", "신청기간"),
            ("application_end", "마감"),
        ),
    )
    if not notice:
        return None

    notice.body = _body(
        row,
        ("description", "설명"),
        ("eligibility", "지원자격"),
        ("target_description", "대상"),
        ("application_method", "신청방법"),
        ("required_documents", "제출서류"),
        ("contact", "문의"),
        ("link", "신청링크"),
    )
    notice.extra = _extra(
        row,
        "id",
        "foundation",
        "category",
        "amount",
        "application_start",
        "application_end",
        "application_period",
        "link",
        "thumbnail_url",
        "attachments",
    )
    return notice


def make_activity_notice(site_id: str, row: dict[str, Any]) -> RawNotice | None:
    return _make_activity_like_notice(site_id, row, kind="activities")


def make_contest_notice(site_id: str, row: dict[str, Any]) -> RawNotice | None:
    return _make_activity_like_notice(site_id, row, kind="contests")


def _make_activity_like_notice(
    site_id: str,
    row: dict[str, Any],
    *,
    kind: str,
) -> RawNotice | None:
    raw_title = _first(row, "title")
    organization = _first(row, "organization")
    title = raw_title
    if organization and organization not in raw_title:
        title = f"[{organization}] {raw_title}"

    notice = make_notice(
        site_id=site_id,
        title=title,
        url=_detail_url(kind, row.get("id")),
        posted_at=_first(row, "created_at", "updated_at", "deadline") or None,
        summary=_summary(
            row,
            ("organization", "주관"),
            ("category", "분류"),
            ("deadline", "마감"),
            ("activity_period", "활동기간"),
            ("recruitment_period", "모집기간"),
        ),
    )
    if not notice:
        return None

    notice.body = _body(
        row,
        ("content", "내용"),
        ("benefits", "혜택"),
        ("target_audience", "대상"),
        ("application_method", "신청방법"),
        ("website_url", "신청링크"),
        ("source_url", "원문"),
        ("contact_email", "문의"),
    )
    notice.extra = _extra(
        row,
        "id",
        "linkareer_id",
        "type",
        "organization",
        "category",
        "deadline",
        "website_url",
        "source_url",
        "image_url",
        "attachments",
    )
    return notice


def _supabase_credentials(ctx: ScrapeContext) -> SupabaseCredentials:
    cache_key = urlparse(ctx.site.url).netloc
    if cache_key in _CREDENTIAL_CACHE:
        return _CREDENTIAL_CACHE[cache_key]

    resp = ctx.client.get(ctx.site.url)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    parts = [html]
    for script in soup.select("script[src]"):
        src = script.get("src")
        if not src:
            continue
        script_url = urljoin(ctx.site.url, src)
        script_resp = ctx.client.get(script_url)
        script_resp.raise_for_status()
        parts.append(script_resp.text)

    joined = "\n".join(parts)
    url_match = SUPABASE_URL_RE.search(joined)
    key_match = SUPABASE_JWT_RE.search(joined)
    if not url_match or not key_match:
        raise ValueError("TheDream Supabase credentials were not found in frontend assets")

    credentials = SupabaseCredentials(url=url_match.group(0), anon_key=key_match.group(0))
    _CREDENTIAL_CACHE[cache_key] = credentials
    return credentials


def _detail_url(kind: str, row_id: Any) -> str | None:
    if not row_id:
        return None
    return f"https://www.thedreamkorea.com/{kind}/{row_id}"


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _to_text(row.get(key))
        if text:
            return text
    return ""


def _summary(row: dict[str, Any], *fields: tuple[str, str]) -> str:
    lines = []
    for key, label in fields:
        value = _to_text(row.get(key))
        if value:
            lines.append(f"{label}: {value}")
    return " / ".join(lines)


def _body(row: dict[str, Any], *fields: tuple[str, str]) -> str:
    lines = []
    for key, label in fields:
        value = _to_text(row.get(key))
        if value:
            lines.append(f"[{label}]\n{value}")
    return "\n\n".join(lines)


def _extra(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "", [], {})}


def _to_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        return compact_text(", ".join(_to_text(item) for item in value if _to_text(item)))
    if isinstance(value, dict):
        return compact_text(
            ", ".join(
                f"{key}: {_to_text(item)}"
                for key, item in value.items()
                if _to_text(item)
            )
        )
    return compact_text(str(value))
