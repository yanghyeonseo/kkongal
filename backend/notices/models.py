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
    matched_keywords = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    is_saved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "notice_id"],
                name="unique_user_notice_inbox",
            )
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.notice_id}"
