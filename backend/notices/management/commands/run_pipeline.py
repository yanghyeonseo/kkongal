"""전체 파이프라인을 한 번에 실행한다: (크롤링) → AI 선별 → 알림 발송.

스케줄러(cron 등)에서 주기적으로 부르기 좋은 단일 진입점.

    # 이미 저장된 공지에 대해 선별 + 발송만 (라이브 크롤링 없음, 빠름/안전)
    python manage.py run_pipeline

    # 라이브 크롤링부터 끝까지
    python manage.py run_pipeline --crawl

    # 특정 단계만 건너뛰기
    python manage.py run_pipeline --crawl --no-dispatch

각 단계는 격리되어, 한 단계 실패가 다음 단계를 막지 않도록 로그를 남기고 이어간다
(단, 치명 오류는 종료 코드에 반영). 개별 옵션은 각 서브커맨드로 전달된다.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the full pipeline: (crawl) -> classify (AI) -> dispatch (email/slack)."

    def add_arguments(self, parser):
        parser.add_argument("--crawl", action="store_true", help="라이브 크롤링부터 시작(느림, 외부 사이트 의존)")
        parser.add_argument("--no-classify", action="store_true", help="AI 선별 단계 건너뛰기")
        parser.add_argument("--no-dispatch", action="store_true", help="알림 발송 단계 건너뛰기")
        parser.add_argument("--source", help="크롤/선별을 특정 출처로 제한(옵션)")
        parser.add_argument("--limit", type=int, help="선별/발송 처리 상한(옵션)")
        parser.add_argument("--dry-run", action="store_true", help="발송/저장 없이 시뮬레이션(가능한 단계에 한해)")

    def _step(self, title: str, command: str, **kwargs) -> bool:
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n▶ {title}"))
        try:
            call_command(command, **{k: v for k, v in kwargs.items() if v is not None})
            return True
        except Exception as exc:  # noqa: BLE001 - 단계 격리
            self.stderr.write(self.style.ERROR(f"  '{command}' 단계 실패: {exc!r}"))
            return False

    def handle(self, *args, **opts):
        ok = True

        if opts["crawl"]:
            ok = self._step(
                "크롤링 (crawl_notices)", "crawl_notices",
                source=opts.get("source"),
            ) and ok

        if not opts["no_classify"]:
            ok = self._step(
                "AI 선별 (classify_notices)", "classify_notices",
                source=opts.get("source"), limit=opts.get("limit"),
                dry_run=opts.get("dry_run") or None,
            ) and ok

        if not opts["no_dispatch"]:
            ok = self._step(
                "알림 발송 (dispatch_alerts)", "dispatch_alerts",
                limit=opts.get("limit"), dry_run=opts.get("dry_run") or None,
            ) and ok

        self.stdout.write(
            self.style.SUCCESS("\n✔ 파이프라인 완료")
            if ok else self.style.WARNING("\n⚠ 파이프라인 일부 단계 실패(로그 참고)")
        )
