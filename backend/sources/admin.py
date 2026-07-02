from django.contrib import admin

from .models import NoticeSource, SourceSubscription


@admin.register(NoticeSource)
class NoticeSourceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "url",
        "crawl_interval_minutes",
        "crawled_at",
        "created_at",
    )
    search_fields = ("name", "url")
    ordering = ("name",)


@admin.register(SourceSubscription)
class SourceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "source_id")
    search_fields = ("user_id__username", "source_id__name", "source_id__url")
    ordering = ("id",)
