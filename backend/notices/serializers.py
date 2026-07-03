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
            "summary",
            "content_markdown",
            "publisher",
            "published_at",
            "deadline_at",
            "updated_at",
            "created_at",
        )
        read_only_fields = fields


class InboxNoticeSerializer(serializers.ModelSerializer):
    notice = NoticeSerializer(source="notice_id", read_only=True)
    deadline_at = serializers.DateTimeField(source="notice_id.deadline_at", read_only=True)

    class Meta:
        model = InboxNotice
        fields = (
            "id",
            "user_id",
            "notice_id",
            "notice",
            "deadline_at",
            "relevance_score",
            "is_recommended",
            "matched_keywords",
            "reason",
            "is_read",
            "is_saved",
        )
        read_only_fields = fields


class InboxNoticeSaveSerializer(serializers.Serializer):
    is_saved = serializers.BooleanField()


class InboxNoticeReadSerializer(serializers.Serializer):
    # 기본값 True: 공지를 열면(별도 값 없이 호출) 읽음 처리한다.
    is_read = serializers.BooleanField(required=False, default=True)
