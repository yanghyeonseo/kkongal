"""데모/개발용 시드 데이터.

라이브 크롤링 없이도 AI 선별 → 알림 파이프라인을 시연/검증할 수 있도록
사용자 · 출처 · 구독 · 관심사 · 공지를 만들어 둔다. 멱등(get_or_create)하게 동작한다.

    python manage.py seed_demo
    python manage.py seed_demo --email you@example.com --reset

이후:
    python manage.py classify_notices     # AI 선별 → inbox_notice
    python manage.py dispatch_alerts       # 이메일/슬랙 발송
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from account.models import Interest
from alert.models import AlertChannel
from notices.models import Notice
from sources.models import NoticeSource, SourceSubscription

User = get_user_model()


# (name, url) — 크롤러 config 의 실제 출처와 느슨하게 맞춘 데모 출처
DEMO_SOURCES = [
    ("서울대 컴퓨터공학부 공지", "https://cse.snu.ac.kr/community/notice"),
    ("사람인 HOT100", "https://www.saramin.co.kr/zf_user/jobs/hot100"),
    ("더드림코리아 장학금", "https://www.thedreamkorea.com/scholarships?tab=all"),
]

# (source_index, title, content, publisher, published_days_ago, deadline_days_from_now)
DEMO_NOTICES = [
    (0, "2026학년도 1학기 컴퓨터공학부 졸업논문 제출 안내",
     "졸업을 앞둔 학부생 대상 졸업논문 제출 일정 및 양식 안내입니다. 지도교수 승인 후 제출하세요.",
     "서울대 컴퓨터공학부", 1, 14),
    (0, "[장학] 소프트웨어 인재 장학금 신청 접수",
     "SW 분야 학부생을 위한 등록금 전액 장학금. 성적 및 포트폴리오 심사. AI/머신러닝 프로젝트 경험 우대.",
     "서울대 컴퓨터공학부", 2, 10),
    (1, "네이버 2026 신입 개발자 공개채용 (백엔드/AI)",
     "네이버 신입 백엔드 및 AI 엔지니어 공개채용. Python, Django, 머신러닝 경험자 우대. 서울 근무.",
     "사람인", 0, 7),
    (1, "카카오 프론트엔드 인턴 모집 (React)",
     "카카오 프론트엔드 인턴십. React, TypeScript 사용. 3개월 인턴 후 정규직 전환 기회.",
     "사람인", 1, 5),
    (1, "삼성전자 반도체 공정 엔지니어 채용",
     "반도체 공정 설계 엔지니어 채용. 재료/화학 전공. 기흥/화성 근무.",
     "사람인", 3, 20),
    (2, "글로벌 IT 기업 SW 개발 장학생 선발",
     "컴퓨터공학·소프트웨어 전공 대학생 대상 장학금 및 인턴 연계 프로그램. AI 관심자 환영.",
     "더드림코리아", 1, 12),
]


class Command(BaseCommand):
    help = "Seed demo data (user, sources, subscriptions, interests, notices) for the AI+alert pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="demo@kkongal.cloud", help="Demo user email (used for email alerts)")
        parser.add_argument("--username", default="demo", help="Demo user username")
        parser.add_argument("--password", default="demo1234!", help="Demo user password")
        parser.add_argument("--slack-webhook", default="", help="Optional Slack webhook URL to seed a Slack channel")
        parser.add_argument("--reset", action="store_true", help="Delete this user's notices/inbox/interests first")

    def handle(self, *args, **opts):
        now = timezone.now()

        user, created = User.objects.get_or_create(
            username=opts["username"],
            defaults={"email": opts["email"]},
        )
        if created:
            user.set_password(opts["password"])
        # keep email in sync so alerts have a destination
        user.email = opts["email"]
        user.job = user.job or "소프트웨어 개발자"
        user.save()
        self.stdout.write(self.style.SUCCESS(
            f"user: {user.username} <{user.email}> ({'created' if created else 'exists'})"
        ))

        if opts["reset"]:
            Interest.objects.filter(user_id=user).delete()
            # inbox rows for this user are removed via cascade when notices are removed;
            # remove demo notices explicitly
            Notice.objects.filter(publisher__in={n[3] for n in DEMO_NOTICES}).delete()
            self.stdout.write(self.style.WARNING("reset: cleared demo interests + notices"))

        # sources + subscriptions
        sources: list[NoticeSource] = []
        for name, url in DEMO_SOURCES:
            src, _ = NoticeSource.objects.get_or_create(url=url, defaults={"name": name})
            if not src.name:
                src.name = name
                src.save(update_fields=["name"])
            sources.append(src)
            SourceSubscription.objects.get_or_create(user_id=user, source_id=src)
        self.stdout.write(self.style.SUCCESS(f"sources+subscriptions: {len(sources)}"))

        # interests (keyword + natural-language description + priority)
        demo_interests = [
            ("백엔드", "Python/Django 기반 백엔드 개발 채용에 관심이 많습니다.", 3),
            ("AI", "머신러닝·인공지능 관련 채용, 장학, 프로젝트 기회를 찾습니다.", 3),
            ("장학금", "소프트웨어/컴퓨터공학 전공 장학금 정보를 받고 싶습니다.", 2),
        ]
        for kw, desc, prio in demo_interests:
            Interest.objects.get_or_create(
                user_id=user, keyword=kw,
                defaults={"description": desc, "priority": prio},
            )
        self.stdout.write(self.style.SUCCESS(f"interests: {len(demo_interests)}"))

        # notices
        made = 0
        for si, title, content, publisher, days_ago, deadline_in in DEMO_NOTICES:
            src = sources[si]
            url = f"{src.url}#demo-{abs(hash(title)) % 100000}"
            _, created_notice = Notice.objects.get_or_create(
                source_id=src, url=url,
                defaults={
                    "title": title,
                    "content": content,
                    "publisher": publisher,
                    "published_at": now - timedelta(days=days_ago),
                    "deadline_at": now + timedelta(days=deadline_in),
                },
            )
            made += int(created_notice)
        self.stdout.write(self.style.SUCCESS(f"notices: {made} new (of {len(DEMO_NOTICES)})"))

        # email alert channel (destination = user's email)
        AlertChannel.objects.get_or_create(
            user_id=user, type=AlertChannel.ChannelType.EMAIL,
            defaults={"config": {"address": user.email}, "is_active": True},
        )
        if opts["slack_webhook"]:
            AlertChannel.objects.get_or_create(
                user_id=user, type=AlertChannel.ChannelType.SLACK,
                defaults={"config": {"webhook_url": opts["slack_webhook"]}, "is_active": True},
            )
        self.stdout.write(self.style.SUCCESS("alert channels ready (email" + (" + slack" if opts["slack_webhook"] else "") + ")"))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nNext:\n  python manage.py classify_notices\n  python manage.py dispatch_alerts\n"
        ))
