from django.conf import settings
from django.db import models
from django.utils import timezone

from notices.models import InboxNotice


class AlertChannel(models.Model):
    class ChannelType(models.TextChoices):
        EMAIL = "email", "Email"
        SLACK = "slack", "Slack"
        KAKAO = "kakao", "Kakao"

    user_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="alert_channels",
    )
    type = models.CharField(max_length=32, choices=ChannelType.choices)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "type"]),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.type}"


class AlertLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    inbox_notice_id = models.ForeignKey(
        InboxNotice,
        on_delete=models.CASCADE,
        db_column="inbox_notice_id",
        related_name="alert_logs",
    )
    channel_id = models.ForeignKey(
        AlertChannel,
        on_delete=models.CASCADE,
        db_column="channel_id",
        related_name="alert_logs",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["sent_at"]),
        ]

    def __str__(self):
        return f"{self.inbox_notice_id} via {self.channel_id} - {self.status}"
