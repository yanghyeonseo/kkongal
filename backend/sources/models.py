from django.db import models
from django.conf import settings
from django.utils import timezone


class NoticeSource(models.Model):
    # 사람이 읽는 표시명(사용자 편집 가능). 등록 시 카탈로그 이름이나 도메인에서 채운다.
    name = models.CharField(max_length=128, blank=True)
    url = models.URLField(max_length=1024, unique=True)
    # 사이트 파비콘 URL. 등록 시 Google s2 서비스로 계산해 저장한다(사이트를 직접 받지 않음).
    favicon_url = models.URLField(max_length=1024, blank=True)
    crawl_interval_minutes = models.IntegerField(default=60)
    crawled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class SourceSubscription(models.Model):
    user_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="source_subscriptions",
    )
    source_id = models.ForeignKey(
        NoticeSource,
        on_delete=models.CASCADE,
        db_column="source_id",
        related_name="subscriptions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "source_id"],
                name="unique_user_source_subscription",
            )
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.source_id}"
