from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AlertChannel, AlertLog
from .serializers import AlertChannelSerializer, AlertLogSerializer


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
        description="로그인한 사용자의 알림 채널 설정을 생성합니다.",
        request=AlertChannelSerializer,
        responses={
            201: AlertChannelSerializer,
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
            return Response(
                AlertChannelSerializer(channel).data,
                status=status.HTTP_201_CREATED,
            )
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
