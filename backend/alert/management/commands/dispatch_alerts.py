"""``dispatch_alerts`` 관리 명령.

미발송(``notified_at IS NULL``) + 관련도 임계값 이상인 inbox 공지를 각 사용자의
활성 알림 채널로 발송한다. 스케줄러(cron 등)가 주기적으로 호출하는 진입점.

예::

    python manage.py dispatch_alerts
    python manage.py dispatch_alerts --user alice --limit 50
    python manage.py dispatch_alerts --dry-run
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from alert.models import AlertChannel
from alert.service import _group_by_user, _pending_queryset, dispatch_pending

User = get_user_model()


class Command(BaseCommand):
    help = "미발송 inbox 공지를 사용자의 활성 알림 채널(이메일/슬랙)로 발송합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="user",
            default=None,
            help="특정 사용자에게만 발송(사용자 id 또는 username).",
        )
        parser.add_argument(
            "--limit",
            dest="limit",
            type=int,
            default=None,
            help="처리할 미발송 inbox 공지 최대 개수.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="실제 발송 없이 발송 대상만 미리 보여줍니다.",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("user"))
        limit = options.get("limit")

        if options.get("dry_run"):
            self._dry_run(user=user, limit=limit)
            return

        summary = dispatch_pending(user=user, limit=limit)
        self.stdout.write(self.style.SUCCESS("알림 발송 완료"))
        self.stdout.write(
            "  시도(attempted): {attempted}\n"
            "  성공(sent):      {sent}\n"
            "  실패(failed):    {failed}\n"
            "  발송 사용자 수:   {users_notified}".format(**summary)
        )

    def _resolve_user(self, raw):
        if not raw:
            return None
        # id 우선, 그다음 username 으로 조회.
        lookup = {}
        if str(raw).isdigit():
            lookup = {"id": int(raw)}
        else:
            lookup = {"username": raw}
        try:
            return User.objects.get(**lookup)
        except User.DoesNotExist as exc:
            raise CommandError(f"사용자를 찾을 수 없습니다: {raw}") from exc

    def _dry_run(self, user, limit):
        pending = list(_pending_queryset(user=user, limit=limit))
        self.stdout.write(
            self.style.WARNING(
                f"[DRY-RUN] 미발송 대상 {len(pending)}건 "
                f"(is_recommended=True 행) — 실제 발송하지 않음"
            )
        )
        grouped = _group_by_user(pending)
        for user_obj, inbox_notices in grouped.values():
            channels = list(
                AlertChannel.objects.filter(user_id=user_obj, is_active=True).order_by(
                    "id"
                )
            )
            channel_desc = (
                ", ".join(f"{c.type}#{c.id}" for c in channels)
                if channels
                else "(활성 채널 없음 → 건너뜀)"
            )
            self.stdout.write(
                f"- 사용자 {user_obj} : 공지 {len(inbox_notices)}건 → 채널 [{channel_desc}]"
            )
            for inbox in inbox_notices:
                notice = inbox.notice_id
                self.stdout.write(
                    f"    · [{inbox.relevance_score:.2f}] {notice.title}"
                )
