from rest_framework import serializers

from .models import AlertChannel, AlertLog


class AlertChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertChannel
        fields = (
            "id",
            "user_id",
            "type",
            "config",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "user_id", "created_at")


class AlertLogSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(
        source="inbox_notice_id.user_id_id",
        read_only=True,
    )
    notice_id = serializers.IntegerField(
        source="inbox_notice_id.notice_id_id",
        read_only=True,
    )

    class Meta:
        model = AlertLog
        fields = (
            "id",
            "user_id",
            "notice_id",
            "inbox_notice_id",
            "channel_id",
            "status",
            "error",
            "sent_at",
        )
        read_only_fields = fields


class AlertChannelTestResponseSerializer(serializers.Serializer):
    """테스트 발송 결과. ok=성공 여부, error=실패 시 사유(성공이면 빈 문자열)."""

    ok = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)
