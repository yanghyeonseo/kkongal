from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Protocol

from . import scrapers
from .config_loader import CrawlerConfig, SiteConfig, load_config
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
