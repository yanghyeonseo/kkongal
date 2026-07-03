from rest_framework import serializers

from .models import NoticeSource, SourceSubscription


class NoticeSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoticeSource
        fields = (
            "id",
            "name",
            "url",
            "favicon_url",
            "crawl_interval_minutes",
            "crawled_at",
            "created_at",
        )
        # favicon_url 은 백엔드가 계산해 저장하므로 응답 전용. name 은 PATCH 로 편집한다.
        read_only_fields = ("id", "favicon_url", "crawled_at", "created_at")


class NoticeSourceNameUpdateSerializer(serializers.Serializer):
    """표시명 편집 입력 검증 — 비어 있지 않고 128자 이하."""

    # CharField 기본값(required=True, allow_blank=False, trim_whitespace=True)이
    # 공백/빈 문자열을 400 으로 막는다. max_length 는 모델 컬럼 길이와 맞춘다.
    name = serializers.CharField(max_length=128)


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
