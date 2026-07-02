"""``run_scheduler`` — 주기적 크롤 → 선별 → 발송 파이프라인 루프.

매 틱마다:
  1. **due 사이트만** 크롤(순진한 매처 OFF). due = ``crawled_at`` 이 그 사이트의
     ``crawl_interval_minutes``(기본 60) 보다 오래됐거나 아직 크롤한 적 없는 사이트.
  2. 신규/미분류 공지를 모든 구독자에 대해 AI 선별(``classify_notices``).
  3. 미발송 + 임계값 이상 inbox 를 활성 알림 채널로 발송(``dispatch_alerts``).

비용 주의(NFR-6): 매 틱은 '새 공지'만 처리한다 — 중복 공지는 저장 단계에서 걸러지고,
이미 AI 로 판정된 (공지,사용자) 쌍은 LLM 을 다시 호출하지 않는다. 그래도 상시 실행은
LLM/이메일/슬랙 비용이 누적되므로, 데모에서는 ``--once`` 나 인터랙티브 '동기화' 버튼
(``POST /api/sources/<id>/sync/``)을 우선 사용하는 것을 권장한다.

예)
    python manage.py run_scheduler                 # 60분 루프(상시)
    python manage.py run_scheduler --interval-minutes 30
    python manage.py run_scheduler --once          # 한 틱만(테스트/수동)
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from crawler.config_loader import load_config
from crawler.repository import DjangoNoticeRepository
from crawler.service import NoticeCrawlService
from sources.models import NoticeSource

log = logging.getLogger("crawler")

_DEFAULT_INTERVAL_MINUTES = 60
# 사이트에 crawl_interval_minutes 가 비어 있을 때의 기본 주기.
_DEFAULT_SOURCE_INTERVAL_MINUTES = 60


class Command(BaseCommand):
    help = (
        "주기적으로 due 사이트를 크롤 → 신규 공지 AI 선별 → 알림 발송하는 스케줄러. "
        "기본 60분 루프이며 --once 로 한 틱만 실행한다(테스트/수동). "
        "비용 주의: 매 틱은 새 공지만 처리하지만 상시 실행은 LLM/이메일/슬랙 비용이 "
        "누적되므로 데모에서는 --once 또는 인터랙티브 동기화 버튼을 권장."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval-minutes",
            type=int,
            default=_DEFAULT_INTERVAL_MINUTES,
            help="틱 사이 대기 시간(분). 기본 60.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="루프 없이 한 틱만 실행하고 종료(테스트/수동 검증용).",
        )

    def handle(self, *args, **options):
        interval_minutes = options["interval_minutes"]
        once = options["once"]

        while True:
            started = timezone.now()
            try:
                self._tick()
            except Exception:  # 한 틱 실패가 루프를 죽이지 않도록
                log.exception("run_scheduler 틱 실패")
                self.stderr.write(
                    self.style.ERROR("틱 실패(로그 참조) — 다음 틱 계속")
                )

            if once:
                break

            elapsed = (timezone.now() - started).total_seconds()
            sleep_seconds = max(0.0, interval_minutes * 60 - elapsed)
            self.stdout.write(
                f"다음 틱까지 {int(sleep_seconds)}s 대기 (interval={interval_minutes}m)"
            )
            time.sleep(sleep_seconds)

    def _tick(self):
        crawled = self._crawl_due_sources()
        # 신규/미분류 공지만 모든 구독자에 대해 선별(NFR-6 로 LLM 비용 상한).
        call_command("classify_notices", stdout=self.stdout, stderr=self.stderr)
        # 미발송 + 임계값 이상 inbox 를 활성 채널로 발송.
        call_command("dispatch_alerts", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write(
            self.style.SUCCESS(f"틱 완료 — 크롤한 사이트 {crawled}곳")
        )

    def _crawl_due_sources(self) -> int:
        due = self._due_sources()
        if not due:
            self.stdout.write("크롤 대상(due) 사이트 없음")
            return 0

        config = load_config()
        site_by_url = {site.url: site for site in config.sites}
        # 순진한 매처 OFF — inbox 편입은 뒤이은 AI 선별만 담당.
        repository = DjangoNoticeRepository(config=config, match_inbox=False)
        service = NoticeCrawlService(config=config, repository=repository)

        crawled = 0
        for source in due:
            site = site_by_url.get(source.url)
            if site is None:
                # 임의 URL 구독 등 자동 수집 미지원 사이트는 건너뛴다.
                continue
            if crawled > 0:
                # 사이트 부하 방지를 위해 크롤 사이에 정중한 지연을 둔다.
                time.sleep(config.defaults.request_delay_seconds)
            try:
                report = service.crawl_site(site.id)
                crawled += 1
                self.stdout.write(
                    f"  크롤 {site.id}: fetched={report.fetched}, "
                    f"new={report.inserted}, dup={report.duplicates}, "
                    f"errors={len(report.errors)}"
                )
            except Exception:
                log.exception("run_scheduler 크롤 실패 (source=%s)", source.id)
                self.stderr.write(
                    self.style.WARNING(f"  크롤 실패: {site.id} (로그 참조)")
                )
        return crawled

    def _due_sources(self) -> list[NoticeSource]:
        """crawled_at 이 사이트별 주기보다 오래됐거나 아직 안 크롤한 NoticeSource."""
        now = timezone.now()
        due: list[NoticeSource] = []
        for source in NoticeSource.objects.all():
            interval = (
                source.crawl_interval_minutes or _DEFAULT_SOURCE_INTERVAL_MINUTES
            )
            if source.crawled_at is None or source.crawled_at <= now - timedelta(
                minutes=interval
            ):
                due.append(source)
        return due
