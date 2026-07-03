from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

from . import scrapers
from .config_loader import CrawlerConfig, SiteConfig
from .dateparse import parse_flexible, to_naive
from .fetcher import http_client
from .schemas import CrawlReport, RawNotice
from .scrapers.base import ScrapeContext, Scraper

log = logging.getLogger("crawler")

ScraperResolver = Callable[[str], Scraper]


class NoticeRepository(Protocol):
    def insert_many(self, notices: list[RawNotice]) -> tuple[int, int]:
        ...


class NoticeCrawlService:
    """공지 스크랩·저장 서비스. Django 백엔드가 직접 import 해서 쓴다."""

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
        return self._run(site, lambda: self._scrape_site(site))

    def crawl_recent(
        self,
        source_id: str,
        days: int = 7,
        limit: int = 20,
    ) -> CrawlReport:
        """한 사이트에서 최근 ``days``일 이내 최대 ``limit``건을 최신순으로 스크랩·저장한다.

        sync 엔드포인트(``POST /api/sources/<id>/sync/``)가 호출한다. ``crawl_site`` 와
        동일하게 저장하되, 저장 대상은 ``_select_recent`` 로 추린다(게시일 없으면 최신순 폴백).
        """
        site = self.config.site(source_id)
        return self._run(
            site,
            lambda: self._select_recent(self._scrape_site(site), days=days, limit=limit),
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

    def preview_site(self, source_id: str, limit: int = 10) -> list[RawNotice]:
        return self._scrape_site(self.config.site(source_id))[:limit]

    def _run(self, site: SiteConfig, produce: Callable[[], list[RawNotice]]) -> CrawlReport:
        """``produce`` 로 얻은 공지를 저장하고 CrawlReport 로 묶는 공통 경로.

        스크랩·추림은 try 안에서 실행돼 외부 사이트 장애가 예외 대신 report.errors 로 남는다.
        crawl_site(전체)와 crawl_recent(최근분)가 이 한 곳을 공유한다.
        """
        started = CrawlReport.now_iso()
        errors: list[str] = []
        items: list[RawNotice] = []
        try:
            items = produce()
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
        """게시일 기준 최근 항목을 최신순·상한 적용해 고른다(날짜 없으면 최신순 폴백).

        윈도우 안이 하나도 없으면 날짜 있는 것 중 최신순으로 폴백해 sync 결과가 빈 채로
        나가지 않게 하고, 날짜 없는 항목은 스크랩 순서(대체로 최신순)로 남는 자리를 채운다.
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

    def _scrape_site(self, site: SiteConfig) -> list[RawNotice]:
        with http_client(self.config.defaults) as client:
            ctx = ScrapeContext(site=site, defaults=self.config.defaults, client=client)
            scraper = self.scraper_resolver(site.scraper)
            return list(scraper(ctx))
