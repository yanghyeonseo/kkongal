from django.contrib import admin

from .models import AlertChannel, AlertLog


@admin.register(AlertChannel)
class AlertChannelAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "type", "is_active", "created_at")
    search_fields = ("user_id__username", "user_id__email", "type")
    list_filter = ("type", "is_active", "created_at")
    ordering = ("-created_at", "-id")


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "inbox_notice_id",
        "channel_id",
        "status",
        "sent_at",
    )
    search_fields = (
        "inbox_notice_id__user_id__username",
        "inbox_notice_id__notice_id__title",
        "channel_id__type",
        "error",
    )
    list_filter = ("status", "channel_id__type", "sent_at")
    ordering = ("-sent_at", "-id")
