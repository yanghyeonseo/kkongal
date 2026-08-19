from django.contrib import admin

from .models import InboxNotice, Notice


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_id",
        "title",
        "publisher",
        "published_at",
        "deadline_at",
        "created_at",
    )
    search_fields = ("title", "content", "publisher", "url")
    list_filter = ("source_id", "published_at", "deadline_at", "created_at")
    ordering = ("-published_at", "-created_at")


@admin.register(InboxNotice)
class InboxNoticeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_id",
        "notice_id",
        "relevance_score",
        "is_read",
        "is_saved",
    )
    search_fields = ("user_id__email", "notice_id__title", "matched_keywords", "reason")
    list_filter = ("is_read", "is_saved")
    ordering = ("-id",)
