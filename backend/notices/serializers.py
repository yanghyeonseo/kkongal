from rest_framework import serializers

from sources.serializers import NoticeSourceSerializer

from .models import InboxNotice, Notice


class NoticeSerializer(serializers.ModelSerializer):
    source = NoticeSourceSerializer(source="source_id", read_only=True)

    class Meta:
        model = Notice
        fields = (
            "id",
            "source_id",
            "source",
            "url",
            "hash",
            "title",
            "content",
            "publisher",
            "published_at",
            "updated_at",
            "created_at",
        )
        read_only_fields = fields


class InboxNoticeSerializer(serializers.ModelSerializer):
    notice = NoticeSerializer(source="notice_id", read_only=True)

    class Meta:
        model = InboxNotice
        fields = (
            "id",
            "user_id",
            "notice_id",
            "notice",
            "relevance_score",
            "matched_keywords",
            "reason",
            "is_read",
        )
        read_only_fields = fields
