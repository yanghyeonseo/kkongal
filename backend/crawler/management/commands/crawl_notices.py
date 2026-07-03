from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from crawler.config_loader import load_config
from crawler.repository import DjangoNoticeRepository
from crawler.service import NoticeCrawlService


class Command(BaseCommand):
    help = "Crawl notice sources and optionally save results into the Notice table."

    def add_arguments(self, parser):
        parser.add_argument("--source", help="Source id from crawler/config/sites.json")
        parser.add_argument("--preview", action="store_true", help="Print crawled items without saving")
        parser.add_argument("--limit", type=int, default=5, help="Preview item limit")
        parser.add_argument("--no-match", action="store_true", help="Skip InboxNotice keyword matching")

    def handle(self, *args, **options):
        config = load_config()
        source_id = options.get("source")
        preview = options["preview"]

        if source_id:
            try:
                config.site(source_id)
            except KeyError as exc:
                raise CommandError(str(exc)) from exc

        if preview:
            service = NoticeCrawlService(config=config, repository=None)
            targets = [source_id] if source_id else [site.id for site in config.enabled_sites()]
            for target in targets:
                items = service.preview_site(target, limit=options["limit"])
                payload = [item.model_dump(mode="json") for item in items]
                self.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2))
            return

        repository = DjangoNoticeRepository(config=config, match_inbox=not options["no_match"])
        service = NoticeCrawlService(config=config, repository=repository)
        reports = service.crawl_all(source_id)
        for report in reports:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{report.source_id}: fetched={report.fetched}, "
                    f"inserted={report.inserted}, duplicates={report.duplicates}, "
                    f"errors={len(report.errors)}"
                )
            )
            for error in report.errors:
                self.stdout.write(self.style.WARNING(f"  - {error}"))
