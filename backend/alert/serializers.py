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


class AlertChannelConfirmationSerializer(serializers.Serializer):
    """채널 생성 직후 연동 확인 발송의 best-effort 상태.

    확인 메시지는 백그라운드에서 논블로킹으로 발송되므로, 생성 응답 시점에는 실제
    도착 여부를 알 수 없다. ``pending=True`` 는 '발송을 시도 중'이라는 뜻이고,
    ``ok`` 는 요청을 (낙관적으로) 접수했는지 여부다. 실제 발송 실패는 서버 로그로만
    남으며 채널 생성 자체는 항상 성공한다(무한로딩 방지 위해 SMTP 왕복을 기다리지
    않는다).
    """

    ok = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)
    pending = serializers.BooleanField()


class AlertChannelCreateResponseSerializer(AlertChannelSerializer):
    """채널 생성 응답: 채널 정보 + 연동 확인 발송 상태(confirmation)."""

    confirmation = AlertChannelConfirmationSerializer()

    class Meta(AlertChannelSerializer.Meta):
        fields = AlertChannelSerializer.Meta.fields + ("confirmation",)
