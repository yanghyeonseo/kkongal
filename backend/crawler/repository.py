from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from dateutil import parser as date_parser
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from notices.models import Notice
from sources.models import NoticeSource

from .config_loader import CrawlerConfig, load_config
from .matcher import match_notice_to_subscribers
from .schemas import RawNotice


def parse_notice_datetime(value: Optional[str]):
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

    try:
        guessed = date_parser.parse(value, fuzzy=True)
    except (TypeError, ValueError, OverflowError):
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
    ) -> None:
        self.config = config or load_config()
        self.match_inbox = match_inbox

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
