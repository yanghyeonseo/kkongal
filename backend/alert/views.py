import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AlertChannel, AlertLog
from .senders import get_sender, send_channel_connected_async
from .serializers import (
    AlertChannelCreateResponseSerializer,
    AlertChannelSerializer,
    AlertChannelTestResponseSerializer,
    AlertLogSerializer,
)
from .throttling import TestSendRateThrottle

logger = logging.getLogger("alert")


def login_required_response(request):
    """기본 권한이 AllowAny 이므로 로그인이 필요한 뷰는 인증을 직접 확인한다.

    미인증이면 401 응답을, 인증된 요청이면 ``None`` 을 돌려준다.
    """
    if request.user.is_authenticated:
        return None
    return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)


class AlertChannelListView(APIView):
    @extend_schema(
        summary="알림 채널 목록 조회",
        description="로그인한 사용자의 알림 채널 설정 목록을 조회합니다.",
        responses={200: AlertChannelSerializer(many=True), 401: "Unauthorized"},
    )
    def get(self, request):
        error = login_required_response(request)
        if error:
            return error

        channels = AlertChannel.objects.filter(user_id=request.user).order_by("type", "id")
        serializer = AlertChannelSerializer(channels, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="알림 채널 생성",
        description=(
            "로그인한 사용자의 알림 채널 설정을 생성합니다. 생성 직후 해당 채널로 "
            "연동 확인 메시지를 백그라운드에서 발송하며(논블로킹), 응답은 즉시 201 로 "
            "반환합니다. confirmation 은 실제 도착 여부가 아니라 발송을 시도 중이라는 "
            "best-effort 상태(pending=true)를 담습니다. 확인 메시지 발송이 실패해도 "
            "채널 생성은 성공합니다."
        ),
        request=AlertChannelSerializer,
        responses={
            201: AlertChannelCreateResponseSerializer,
            400: "Bad Request",
            401: "Unauthorized",
        },
    )
    def post(self, request):
        error = login_required_response(request)
        if error:
            return error

        serializer = AlertChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = serializer.save(user_id=request.user)

        # 연동 확인 발송을 요청 스레드에서 동기로 하면 SMTP 왕복 때문에 '추가' 버튼이
        # 무한 로딩된다. 백그라운드로 위임하고 즉시 201 을 반환하며, confirmation 은
        # 실제 도착 여부가 아니라 best-effort 발송 상태(pending)만 담는다.
        try:
            send_channel_connected_async(channel, request.user)
            confirmation = {"ok": True, "error": "", "pending": True}
        except Exception:  # 발송 트리거 실패가 채널 생성을 막지 않도록 방어
            logger.exception("연동 확인 발송 트리거 실패 (채널=%s)", channel.id)
            confirmation = {"ok": False, "error": "", "pending": False}

        data = AlertChannelSerializer(channel).data
        data["confirmation"] = confirmation
        return Response(data, status=status.HTTP_201_CREATED)


class AlertChannelDetailView(APIView):
    def get_channel(self, request, channel_id):
        return get_object_or_404(AlertChannel, id=channel_id, user_id=request.user)

    @extend_schema(
        summary="알림 채널 수정",
        description="로그인한 사용자의 알림 채널 설정을 부분 수정합니다.",
        request=AlertChannelSerializer,
        responses={
            200: AlertChannelSerializer,
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
        },
    )
    def patch(self, request, channel_id):
        error = login_required_response(request)
        if error:
            return error

        channel = self.get_channel(request, channel_id)
        serializer = AlertChannelSerializer(channel, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="알림 채널 삭제",
        description="로그인한 사용자의 알림 채널 설정을 삭제합니다.",
        responses={204: "No Content", 401: "Unauthorized", 404: "Not Found"},
    )
    def delete(self, request, channel_id):
        error = login_required_response(request)
        if error:
            return error

        channel = self.get_channel(request, channel_id)
        channel.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertLogListView(APIView):
    @extend_schema(
        summary="알림 로그 목록 조회",
        description="로그인한 사용자의 알림 발송 로그를 조회합니다.",
        parameters=[
            OpenApiParameter(
                name="status",
                description="pending, sent, failed 중 하나로 필터링합니다.",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="inbox_notice_id",
                description="특정 inbox notice의 알림 로그만 조회합니다.",
                required=False,
                type=int,
            ),
        ],
        responses={
            200: AlertLogSerializer(many=True),
            400: "Bad Request",
            401: "Unauthorized",
        },
    )
    def get(self, request):
        error = login_required_response(request)
        if error:
            return error

        logs = (
            AlertLog.objects.filter(inbox_notice_id__user_id=request.user)
            .select_related(
                "inbox_notice_id",
                "inbox_notice_id__notice_id",
                "channel_id",
            )
            .order_by("-sent_at", "-id")
        )

        log_status = request.query_params.get("status")
        if log_status:
            valid_statuses = {choice[0] for choice in AlertLog.Status.choices}
            if log_status not in valid_statuses:
                return Response(
                    {"detail": "status must be pending, sent, or failed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logs = logs.filter(status=log_status)

        inbox_notice_id = request.query_params.get("inbox_notice_id")
        if inbox_notice_id:
            logs = logs.filter(inbox_notice_id_id=inbox_notice_id)

        serializer = AlertLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AlertChannelTestView(APIView):
    # 테스트 발송은 사용자가 등록한 주소(config.address)/webhook 으로 실제 메일·슬랙을
    # 쏘므로, 임의 수신자 대량발송 악용을 막기 위해 사용자당 가벼운 rate-limit 을 건다.
    throttle_classes = [TestSendRateThrottle]

    @extend_schema(
        summary="알림 채널 테스트 발송",
        description=(
            "지정한 알림 채널의 등록 주소(이메일은 config.address, 없으면 회원 이메일 / "
            "슬랙은 등록 webhook)로 친근한 테스트 메시지를 발송해 연결 상태를 확인합니다. "
            "실제 공지가 아닌 테스트이므로 AlertLog 는 남기지 않습니다. 응답의 ok 로 "
            "성공 여부를, error 로 실패 사유를 확인합니다. 사용자당 요청 빈도가 제한됩니다."
        ),
        request=None,
        responses={
            200: AlertChannelTestResponseSerializer,
            401: "Unauthorized",
            404: "Not Found",
            429: "Too Many Requests",
        },
    )
    def post(self, request, channel_id):
        auth_error = login_required_response(request)
        if auth_error:
            return auth_error

        # 소유하지 않은 채널이면 404 (다른 alert 뷰와 동일한 패턴).
        channel = get_object_or_404(AlertChannel, id=channel_id, user_id=request.user)

        sender = get_sender(channel)
        if sender is None:
            return Response(
                {"ok": False, "error": f"지원하지 않는 채널 타입: {channel.type}"},
                status=status.HTTP_200_OK,
            )

        ok, error = sender.send_test(request.user)
        return Response({"ok": ok, "error": error}, status=status.HTTP_200_OK)
