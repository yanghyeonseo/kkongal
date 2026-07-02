from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class RawNotice(BaseModel):
    """공지 한 건의 표준 페이로드 — 모든 스크래퍼는 이 형태로 반환한다."""

    source_id: str
    title: str
    url: HttpUrl
    posted_at: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    extra: dict = Field(default_factory=dict)

    def content_hash(self) -> str:
        key = f"{self.source_id}|{str(self.url).strip()}|{self.title.strip()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


class StoredNotice(BaseModel):
    id: int
    source_id: str
    title: str
    url: str
    posted_at: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    hash: str
    fetched_at: str


class CrawlReport(BaseModel):
    source_id: str
    fetched: int
    inserted: int
    duplicates: int
    errors: list[str] = Field(default_factory=list)
    started_at: str
    finished_at: str

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
