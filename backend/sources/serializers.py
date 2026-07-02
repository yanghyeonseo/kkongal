from rest_framework import serializers

from .models import NoticeSource, SourceSubscription


class NoticeSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoticeSource
        fields = (
            "id",
            "name",
            "url",
            "crawl_interval_minutes",
            "crawled_at",
            "created_at",
        )
        read_only_fields = ("id", "crawled_at", "created_at")


class SourceSubscriptionSerializer(serializers.ModelSerializer):
    source = NoticeSourceSerializer(source="source_id", read_only=True)

    class Meta:
        model = SourceSubscription
        fields = (
            "id",
            "user_id",
            "source_id",
            "source",
        )
        read_only_fields = ("id", "user_id", "source_id", "source")


class SourceSubscriptionCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=1024)
