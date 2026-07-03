from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

from . import scrapers
from .config_loader import CrawlerConfig, SiteConfig, load_config
from .dateparse import parse_flexible, to_naive
from .fetcher import http_client
from .schemas import CrawlReport, RawNotice, StoredNotice
from .scrapers.base import ScrapeContext, Scraper

log = logging.getLogger("crawler")

ScraperResolver = Callable[[str], Scraper]


class NoticeRepository(Protocol):
    def insert_many(self, notices: list[RawNotice]) -> tuple[int, int]:
        ...

    def list_notices(
        self,
        source_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoredNotice]:
        ...

    def count(self, source_id: Optional[str] = None) -> int:
        ...

    def delete_all(self) -> None:
        ...


class NoticeCrawlService:
    """통합 백엔드가 직접 import 해서 쓸 내부 서비스."""

    def __init__(
        self,
        config: CrawlerConfig,
        repository: Optional[NoticeRepository] = None,
        scraper_resolver: ScraperResolver = scrapers.get,
    ) -> None:
        self.config = config
        self.repository = repository
        self.scraper_resolver = scraper_resolver

    def crawl_site(self, source_id: str) -> CrawlReport:
        site = self.config.site(source_id)
        started = CrawlReport.now_iso()
        errors: list[str] = []
        items: list[RawNotice] = []

        try:
            items = self._scrape_site(site)
        except Exception as exc:  # noqa: BLE001 - 외부 사이트 장애는 리포트로 남긴다.
            errors.append(f"fetch/parse failed: {exc!r}")

        inserted = duplicates = 0
        if items and self.repository:
            inserted, duplicates = self.repository.insert_many(items)

        return CrawlReport(
            source_id=site.id,
            fetched=len(items),
            inserted=inserted,
            duplicates=duplicates,
            errors=errors,
            started_at=started,
            finished_at=CrawlReport.now_iso(),
        )

    def crawl_all(self, source_id: Optional[str] = None) -> list[CrawlReport]:
        reports: list[CrawlReport] = []
        targets = [self.config.site(source_id)] if source_id else list(self.config.enabled_sites())
        for i, site in enumerate(targets):
            if i > 0:
                time.sleep(self.config.defaults.request_delay_seconds)
            log.info("crawl start: %s", site.id)
            report = self.crawl_site(site.id)
            log.info(
                "crawl done: %s - fetched=%d inserted=%d dup=%d errors=%d",
                site.id, report.fetched, report.inserted, report.duplicates, len(report.errors),
            )
            reports.append(report)
        return reports

    def list_sources(self, enabled_only: bool = False) -> list[SiteConfig]:
        if enabled_only:
            return list(self.config.enabled_sites())
        return list(self.config.sites)

    def preview_site(self, source_id: str, limit: int = 10) -> list[RawNotice]:
        return self._scrape_site(self.config.site(source_id))[:limit]

    def crawl_recent(
        self,
        source_id: str,
        days: int = 7,
        limit: int = 20,
    ) -> CrawlReport:
        """한 사이트에서 "최근 ``days``일 이내, 최대 ``limit``건"을 최신순으로 스크랩·저장한다.

        sync 엔드포인트(``POST /api/sources/<id>/sync/``)가 호출한다. ``crawl_site`` 와
        동일하게 self.repository 로 저장하고 CrawlReport 를 돌려주되, 저장 대상은
        ``_select_recent`` 로 최근 항목(최대 limit)만 추린다(게시일 없으면 최신순 폴백).
        원본 RawNotice 선택 로직만 필요하면 정적 ``_select_recent`` 를 직접 쓰면 된다.
        """
        site = self.config.site(source_id)
        started = CrawlReport.now_iso()
        errors: list[str] = []
        items: list[RawNotice] = []
        try:
            scraped = self._scrape_site(site)
            items = self._select_recent(scraped, days=days, limit=limit)
        except Exception as exc:  # noqa: BLE001 - 외부 사이트 장애는 리포트로 남긴다.
            errors.append(f"fetch/parse failed: {exc!r}")

        inserted = duplicates = 0
        if items and self.repository:
            inserted, duplicates = self.repository.insert_many(items)

        return CrawlReport(
            source_id=site.id,
            fetched=len(items),
            inserted=inserted,
            duplicates=duplicates,
            errors=errors,
            started_at=started,
            finished_at=CrawlReport.now_iso(),
        )

    @staticmethod
    def _select_recent(
        items: list[RawNotice],
        *,
        days: int,
        limit: int,
    ) -> list[RawNotice]:
        """게시일 기준으로 최근 항목을 골라 최신순·상한 적용한다(날짜 없으면 최신순 폴백).

        - 날짜가 있는 항목: ``days`` 윈도우 안의 것들을 최신순으로.
          윈도우 안이 하나도 없으면(모두 오래된 경우) 날짜 있는 것 중 최신순으로 폴백해
          sync 결과가 빈 채로 나가지 않게 한다.
        - 날짜가 없는 항목: 스크랩 순서(사이트가 대체로 최신순 제공)를 최신으로 보고
          남는 자리에 채운다.
        """
        now = datetime.now()
        cutoff = now - timedelta(days=days)

        dated: list[tuple[datetime, RawNotice]] = []
        undated: list[RawNotice] = []
        for item in items:
            parsed = to_naive(parse_flexible(item.posted_at, now=now)) if item.posted_at else None
            if parsed is None:
                undated.append(item)
            else:
                dated.append((parsed, item))

        result: list[RawNotice] = []
        if dated:
            within = sorted(
                (pair for pair in dated if pair[0] >= cutoff),
                key=lambda pair: pair[0],
                reverse=True,
            )
            chosen = within or sorted(dated, key=lambda pair: pair[0], reverse=True)
            result = [item for _, item in chosen]

        for item in undated:
            if len(result) >= limit:
                break
            result.append(item)

        return result[:limit]

    def list_notices(
        self,
        source_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoredNotice]:
        if not self.repository:
            return []
        return self.repository.list_notices(source_id=source_id, limit=limit, offset=offset)

    def count_notices(self, source_id: Optional[str] = None) -> int:
        if not self.repository:
            return 0
        return self.repository.count(source_id=source_id)

    def delete_all_notices(self) -> None:
        if self.repository:
            self.repository.delete_all()

    def _scrape_site(self, site: SiteConfig) -> list[RawNotice]:
        with http_client(self.config.defaults) as client:
            ctx = ScrapeContext(site=site, defaults=self.config.defaults, client=client)
            scraper = self.scraper_resolver(site.scraper)
            return list(scraper(ctx))


def build_service(
    config: Optional[CrawlerConfig] = None,
    repository: Optional[NoticeRepository] = None,
) -> NoticeCrawlService:
    """크롤링 서비스를 만든다. Django 저장소는 나중에 repository로 주입한다."""

    return NoticeCrawlService(
        config=config or load_config(),
        repository=repository,
    )
