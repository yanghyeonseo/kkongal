"""generic 파이프라인 실측 검증 명령.

임의 사이트 URL 들을 실제로 크롤해 DB 에 저장하고, Notice 의 각 컬럼이 얼마나
채워졌는지 리포트한다. "코드만 쓰고 끝"이 아니라 실제 DB 적재를 눈으로 확인하기 위한
도구다. 선택적으로 --enrich 로 AI 보강까지 돌려 summary/content_markdown 채움도 본다.

    DEBUG=True .venv/bin/python manage.py verify_generic \
        https://news.ycombinator.com/rss https://example.com/ --enrich

각 URL 마다 NoticeSource 를 (없으면) 만들고 crawl_source 로 크롤한 뒤, 그 소스의
Notice 들에 대해 컬럼별 채움 비율을 출력한다.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from crawler.config_loader import load_config
from crawler.repository import DjangoNoticeRepository
from crawler.service import NoticeCrawlService
from notices.models import Notice
from sources.models import NoticeSource

# Notice 에서 "채워졌는지" 확인할 컬럼들(빈 문자열/None 을 미채움으로 본다).
_CHECK_FIELDS = (
    "title",
    "url",
    "hash",
    "content",
    "publisher",
    "published_at",
    "summary",
    "content_markdown",
)


class Command(BaseCommand):
    help = "임의 사이트 URL 들을 generic 파이프라인으로 크롤해 DB 적재를 검증한다."

    def add_arguments(self, parser):
        parser.add_argument("urls", nargs="+", help="크롤할 사이트 URL 들")
        parser.add_argument(
            "--enrich",
            action="store_true",
            help="크롤 후 AI 보강까지 실행해 summary/content_markdown 채움도 검증",
        )
        parser.add_argument(
            "--days", type=int, default=3650, help="최근 N일 창(기본: 사실상 무제한)"
        )
        parser.add_argument("--limit", type=int, default=20, help="사이트당 최대 저장 수")

    def handle(self, *args, **options):
        config = load_config()
        for url in options["urls"]:
            self._run_one(config, url, options)

    def _run_one(self, config, url, options):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {url} ==="))
        source, created = NoticeSource.objects.get_or_create(
            url=url, defaults={"name": url}
        )
        self.stdout.write(
            f"NoticeSource id={source.id} ({'신규' if created else '기존'})"
        )

        repository = DjangoNoticeRepository(
            config=config, match_inbox=False, source_override=source
        )
        service = NoticeCrawlService(config=config, repository=repository)

        report = service.crawl_source(
            source, days=options["days"], limit=options["limit"]
        )
        source.refresh_from_db()
        self.stdout.write(
            f"전략(scraper_kind)={source.scraper_kind or '(none)'} "
            f"render={source.render} profile={source.extraction_profile}"
        )
        self.stdout.write(
            f"크롤 결과: fetched={report.fetched} inserted={report.inserted} "
            f"dup={report.duplicates} errors={report.errors}"
        )

        if options["enrich"]:
            self._enrich(source)

        self._report_fill(source)

    def _enrich(self, source):
        from ai.enrich import enrich_notices

        notices = list(Notice.objects.filter(source_id=source))
        if not notices:
            return
        try:
            enrich_notices(notices)
            self.stdout.write(f"보강 실행: {len(notices)}건")
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"보강 실패: {exc!r}"))

    def _report_fill(self, source):
        notices = list(Notice.objects.filter(source_id=source))
        total = len(notices)
        if total == 0:
            self.stdout.write(self.style.WARNING("저장된 Notice 0건 — 채움 검증 불가"))
            return

        self.stdout.write(self.style.HTTP_INFO(f"저장 {total}건 — 컬럼별 채움:"))
        for field in _CHECK_FIELDS:
            filled = sum(1 for n in notices if _is_filled(getattr(n, field)))
            pct = filled * 100 // total
            style = self.style.SUCCESS if filled == total else (
                self.style.WARNING if filled else self.style.ERROR
            )
            self.stdout.write(style(f"  {field:18} {filled:3}/{total} ({pct}%)"))

        sample = notices[0]
        self.stdout.write("샘플 1건:")
        self.stdout.write(f"  title      = {sample.title[:70]!r}")
        self.stdout.write(f"  url        = {sample.url[:70]!r}")
        self.stdout.write(f"  published  = {sample.published_at}")
        self.stdout.write(f"  content    = {(sample.content or '')[:70]!r}")
        self.stdout.write(f"  summary    = {(sample.summary or '')[:70]!r}")


def _is_filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True
