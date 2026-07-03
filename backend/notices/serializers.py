from rest_framework import serializers
from django.contrib.auth import get_user_model

from sources.serializers import NoticeSourceSerializer

from .models import InboxNotice, Notice

User = get_user_model()


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


class AiCandidateInterestSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    keyword = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    priority = serializers.IntegerField()


class AiNoticeCandidateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    age = serializers.IntegerField(allow_null=True)
    job = serializers.CharField(allow_blank=True)
    gender = serializers.CharField(allow_blank=True)
    interests = AiCandidateInterestSerializer(many=True)


class AiInboxNoticeCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    notice_id = serializers.IntegerField()
    relevance_score = serializers.FloatField(required=False, default=0.0)
    matched_keywords = serializers.JSONField(required=False, default="")
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        try:
            attrs["user"] = User.objects.get(id=attrs["user_id"])
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"user_id": "User does not exist."}
            ) from exc

        try:
            attrs["notice"] = Notice.objects.get(id=attrs["notice_id"])
        except Notice.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"notice_id": "Notice does not exist."}
            ) from exc

        matched_keywords = attrs.get("matched_keywords", "")
        if isinstance(matched_keywords, list):
            attrs["matched_keywords"] = ",".join(str(item) for item in matched_keywords)
        elif matched_keywords is None:
            attrs["matched_keywords"] = ""
        elif not isinstance(matched_keywords, str):
            attrs["matched_keywords"] = str(matched_keywords)

        return attrs
