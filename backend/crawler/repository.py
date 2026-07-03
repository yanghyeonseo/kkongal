from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from notices.models import Notice
from sources.models import NoticeSource

from .config_loader import CrawlerConfig, load_config
from .dateparse import parse_flexible
from .matcher import match_notice_to_subscribers
from .schemas import RawNotice


def parse_notice_datetime(value: Optional[str]):
    """스크래퍼가 넘긴 게시일 문자열을 tz-aware ``datetime`` 으로 변환한다.

    ISO 는 빠른 경로로 처리하고, 그 외 사이트별 형식(``2026/7/01``,
    ``2026.06.23 12:00:00``)과 상대표현(``6일 전 등록``)은 :func:`crawler.dateparse.parse_flexible`
    로 위임한다.
    """
    if not value:
        return None

    parsed_datetime = parse_datetime(value)
    if parsed_datetime:
        if timezone.is_naive(parsed_datetime):
            return timezone.make_aware(parsed_datetime)
        return parsed_datetime

    parsed_date = parse_date(value)
    if parsed_date:
        return timezone.make_aware(datetime.combine(parsed_date, time.min))

    guessed = parse_flexible(value)
    if guessed is None:
        return None
    if timezone.is_naive(guessed):
        return timezone.make_aware(guessed)
    return guessed


class DjangoNoticeRepository:
    """Persist crawler RawNotice objects into the existing Notice models."""

    def __init__(
        self,
        config: Optional[CrawlerConfig] = None,
        *,
        match_inbox: bool = True,
        source_override: Optional[NoticeSource] = None,
    ) -> None:
        self.config = config or load_config()
        self.match_inbox = match_inbox
        # generic(임의 사이트) 크롤은 항상 단일 소스라, config 카탈로그에 없는 source_id
        # 토큰 대신 이 NoticeSource 를 직접 붙인다. 설정되면 모든 공지가 이 소스에 귀속된다.
        self.source_override = source_override

    def insert_many(self, notices: list[RawNotice]) -> tuple[int, int]:
        inserted = 0
        duplicates = 0
        touched_sources: set[int] = set()

        for raw_notice in notices:
            source = self._get_or_create_source(raw_notice.source_id)
            notice, created = Notice.objects.get_or_create(
                source_id=source,
                url=str(raw_notice.url),
                defaults={
                    "hash": raw_notice.content_hash(),
                    "title": raw_notice.title.strip(),
                    "content": raw_notice.body or raw_notice.summary or "",
                    "publisher": source.name,
                    "published_at": parse_notice_datetime(raw_notice.posted_at),
                },
            )

            touched_sources.add(source.id)
            if created:
                inserted += 1
                if self.match_inbox:
                    match_notice_to_subscribers(notice)
            else:
                duplicates += 1

        if touched_sources:
            NoticeSource.objects.filter(id__in=touched_sources).update(crawled_at=timezone.now())

        return inserted, duplicates

    def _get_or_create_source(self, source_id: str) -> NoticeSource:
        # generic 크롤: config 조회 없이 등록 시 만들어진 NoticeSource 를 그대로 쓴다.
        if self.source_override is not None:
            return self.source_override
        site = self.config.site(source_id)
        source, _ = NoticeSource.objects.get_or_create(
            url=site.url,
            defaults={
                "name": site.name,
            },
        )
        if not source.name:
            source.name = site.name
            source.save(update_fields=["name"])
        return source
