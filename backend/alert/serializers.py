from urllib.parse import urlparse

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework import serializers

from .models import AlertChannel, AlertLog

# 슬랙 Incoming Webhook 은 항상 이 호스트다. SSRF 방지를 위해 정확히 일치시킨다.
SLACK_WEBHOOK_HOST = "hooks.slack.com"


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

    def validate(self, attrs):
        # 부분 수정(PATCH)에서는 들어오지 않은 값을 기존 인스턴스 값으로 보완한다.
        channel_type = attrs.get("type") or getattr(self.instance, "type", None)
        config = attrs.get("config")
        if config is None:
            config = getattr(self.instance, "config", None) or {}
        if not isinstance(config, dict):
            raise serializers.ValidationError(
                {"config": "config 는 객체(JSON) 형태여야 합니다."}
            )

        if channel_type == AlertChannel.ChannelType.SLACK:
            self._validate_slack_config(config)
        elif channel_type == AlertChannel.ChannelType.EMAIL:
            self._validate_email_config(config)
        return attrs

    @staticmethod
    def _validate_slack_config(config):
        webhook_url = (config.get("webhook_url") or "").strip()
        if not webhook_url:
            raise serializers.ValidationError(
                {"config": "슬랙 채널은 webhook_url 이 필요합니다."}
            )
        # SSRF 방어: 사용자 제공 URL 을 https + hooks.slack.com 으로만 제한한다.
        parsed = urlparse(webhook_url)
        if parsed.scheme != "https" or parsed.hostname != SLACK_WEBHOOK_HOST:
            raise serializers.ValidationError(
                {
                    "config": "webhook_url 은 https://hooks.slack.com/services/... 형식이어야 합니다."
                }
            )

    @staticmethod
    def _validate_email_config(config):
        address = (config.get("address") or "").strip()
        if not address:
            return  # 미지정이면 회원 이메일로 폴백하므로 허용.
        try:
            validate_email(address)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"config": "유효한 이메일 주소가 아닙니다."}
            ) from exc


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
