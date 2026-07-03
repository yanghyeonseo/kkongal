from django.db import models
from django.conf import settings
from django.utils import timezone

from sources.models import NoticeSource


class Notice(models.Model):
    source_id = models.ForeignKey(
        NoticeSource,
        on_delete=models.CASCADE,
        db_column="source_id",
        related_name="notices",
    )
    url = models.URLField(max_length=1024)
    hash = models.CharField(max_length=256, blank=True)
    title = models.CharField(max_length=256)
    content = models.TextField(blank=True)
    # AI 보강(enrichment) 산출물 — 공지당 1회 채운다(ai/enrich.py). 사용자 무관.
    summary = models.TextField(blank=True)  # 한국어 3문장 요약
    content_markdown = models.TextField(blank=True)  # 원문 정보를 보존한 깔끔한 markdown
    publisher = models.CharField(max_length=128, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_id", "url"],
                name="unique_notice_source_url",
            )
        ]

    def __str__(self):
        return self.title


class InboxNotice(models.Model):
    user_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="inbox_notices",
    )
    notice_id = models.ForeignKey(
        Notice,
        on_delete=models.CASCADE,
        db_column="notice_id",
        related_name="inbox_entries",
    )
    relevance_score = models.FloatField(default=0.0)
    # AI 선별이 임계값(settings.LLM_RELEVANCE_THRESHOLD) 이상으로 판정했는지.
    # 대시보드 '전체 공지'는 모든 행을, 'AI 추천' 탭과 모든 알림은 이 값이 True 인
    # 행만 사용한다. 분류 시 relevance_score >= threshold 로 계산해 저장한다.
    is_recommended = models.BooleanField(default=False)
    matched_keywords = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    is_saved = models.BooleanField(default=False)
    # 알림 발송 시각. null 이면 아직 미발송 → 알림 디스패처의 중복 발송 방지 기준.
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "notice_id"],
                name="unique_user_notice_inbox",
            )
        ]
        indexes = [
            models.Index(fields=["user_id", "created_at"]),
            models.Index(fields=["user_id", "is_read"]),
            models.Index(fields=["user_id", "is_recommended"]),
            models.Index(fields=["notified_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.notice_id}"
