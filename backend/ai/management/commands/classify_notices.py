"""`manage.py classify_notices` — 수집 공지를 LLM(또는 폴백)으로 선별.

파이프라인: crawl_notices → **classify_notices** → dispatch_alerts.

예)
    manage.py classify_notices                     # 신규 공지만
    manage.py classify_notices --since 24h          # 최근 24시간
    manage.py classify_notices --source 3 --limit 50
    manage.py classify_notices --reclassify         # 이미 분류된 쌍도 재판정
    manage.py classify_notices --dry-run            # 쓰지 않고 결과만 집계
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ai.service import run_classification

_RELATIVE_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


class Command(BaseCommand):
    help = "수집된 공지를 LLM(또는 키워드 폴백)으로 선별해 InboxNotice 를 생성/갱신합니다."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help="이 시각 이후 생성된 공지만. ISO datetime 또는 상대표기('30m','24h','7d', 숫자=시간).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="처리할 공지 최대 개수.",
        )
        parser.add_argument(
            "--source",
            type=int,
            default=None,
            dest="source_id",
            help="특정 출처(NoticeSource id)의 공지만 분류.",
        )
        parser.add_argument(
            "--reclassify",
            action="store_true",
            help="이미 분류된 (공지,사용자) 쌍도 다시 판정(LLM 재호출).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="InboxNotice 를 쓰지 않고 집계만 출력.",
        )

    def handle(self, *args, **options) -> None:
        since = self._parse_since(options.get("since"))

        summary = run_classification(
            since=since,
            limit=options.get("limit"),
            source_id=options.get("source_id"),
            reclassify=options.get("reclassify", False),
            dry_run=options.get("dry_run", False),
        )

        prefix = "[dry-run] " if options.get("dry_run") else ""
        lines = [
            f"{prefix}공지 처리: {summary.notices_processed}",
            f"분류 시도(공지×사용자): {summary.candidates}",
            f"inbox 생성: {summary.created}",
            f"inbox 갱신: {summary.updated}",
            f"임계값 미만 제외: {summary.below_threshold}",
            f"다운그레이드 삭제: {summary.downgraded}",
            f"기존 분류 생략: {summary.skipped_existing}",
            f"오류: {summary.errors}",
            f"판정 경로: {summary.provider} "
            f"(llm={summary.llm_calls}, fallback={summary.fallback_calls})",
        ]
        self.stdout.write(self.style.SUCCESS("classify_notices 완료"))
        for line in lines:
            self.stdout.write("  " + line)

    def _parse_since(self, raw):
        if not raw:
            return None

        parsed = parse_datetime(raw)
        if parsed is not None:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(
                    parsed, timezone.get_current_timezone()
                )
            return parsed

        text = raw.strip().lower()
        try:
            unit = text[-1]
            if unit in _RELATIVE_UNITS:
                amount = float(text[:-1])
                return timezone.now() - timedelta(
                    **{_RELATIVE_UNITS[unit]: amount}
                )
            # 단위 없으면 시간으로 해석
            return timezone.now() - timedelta(hours=float(text))
        except (ValueError, IndexError) as exc:
            raise CommandError(f"--since 값을 해석할 수 없습니다: {raw!r}") from exc
