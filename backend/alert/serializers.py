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
