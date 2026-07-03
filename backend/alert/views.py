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


class AlertChannelListView(APIView):
    @extend_schema(
        summary="알림 채널 목록 조회",
        description="로그인한 사용자의 알림 채널 설정 목록을 조회합니다.",
        responses={200: AlertChannelSerializer(many=True), 401: "Unauthorized"},
    )
    def get(self, request):
        author = request.user
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        channels = AlertChannel.objects.filter(user_id=author).order_by("type", "id")
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
        author = request.user
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = AlertChannelSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            channel = serializer.save(user_id=author)
            # 연동 확인 메시지는 SMTP 왕복이 느리거나 멈출 수 있어, 요청 스레드에서
            # 동기로 보내면 '추가' 버튼이 무한 로딩된다(원래 버그). 따라서 발송은
            # 백그라운드(데몬 스레드)에서 논블로킹으로 처리하고 응답은 즉시 201 로
            # 돌려준다. confirmation 은 실제 도착 여부가 아니라 'best-effort 로 발송을
            # 시도 중'이라는 상태(pending)만 담는다.
            try:
                send_channel_connected_async(channel, author)
                confirmation = {"ok": True, "error": "", "pending": True}
            except Exception:  # noqa: BLE001 - 백그라운드 발송 트리거 실패가 생성을 막지 않도록
                logger.exception("연동 확인 발송 트리거 실패 (채널=%s)", channel.id)
                confirmation = {"ok": False, "error": "", "pending": False}
            data = AlertChannelSerializer(channel).data
            data["confirmation"] = confirmation
            return Response(data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AlertChannelDetailView(APIView):
    def get_channel(self, request, channel_id):
        return get_object_or_404(
            AlertChannel,
            id=channel_id,
            user_id=request.user,
        )

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
        author = request.user
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        channel = self.get_channel(request, channel_id)
        serializer = AlertChannelSerializer(channel, data=request.data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="알림 채널 삭제",
        description="로그인한 사용자의 알림 채널 설정을 삭제합니다.",
        responses={204: "No Content", 401: "Unauthorized", 404: "Not Found"},
    )
    def delete(self, request, channel_id):
        author = request.user
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

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
        author = request.user
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        logs = (
            AlertLog.objects.filter(inbox_notice_id__user_id=author)
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
    # (인증된 본인 채널 한정이라 강한 제한은 불필요 — 오남용만 차단.)
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
        author = request.user
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        # 소유하지 않은 채널이면 404 (다른 alert 뷰와 동일한 패턴).
        channel = get_object_or_404(AlertChannel, id=channel_id, user_id=author)

        sender = get_sender(channel)
        if sender is None:
            return Response(
                {"ok": False, "error": f"지원하지 않는 채널 타입: {channel.type}"},
                status=status.HTTP_200_OK,
            )

        ok, error = sender.send_test(author)
        return Response({"ok": ok, "error": error}, status=status.HTTP_200_OK)
