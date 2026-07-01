from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, extend_schema

from .models import InboxNotice
from .serializers import InboxNoticeSaveSerializer, InboxNoticeSerializer


class InboxNoticeListView(APIView):
    @extend_schema(
        summary="공지 목록 조회",
        description="로그인한 사용자의 inbox 공지 목록을 조회합니다.",
        parameters=[
            OpenApiParameter(
                name="saved",
                description="true이면 저장된 공지만, false이면 저장되지 않은 공지만 조회합니다.",
                required=False,
                type=bool,
            )
        ],
        responses={200: InboxNoticeSerializer(many=True), 401: "Unauthorized"},
    )
    def get(self, request):
        author = request.user

        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        inbox_notices = (
            InboxNotice.objects.filter(user_id=author)
            .select_related("notice_id", "notice_id__source_id")
            .order_by("-notice_id__published_at", "-notice_id__created_at", "-id")
        )

        saved = request.query_params.get("saved")
        if saved is not None:
            if saved.lower() in ("true", "1"):
                inbox_notices = inbox_notices.filter(is_saved=True)
            elif saved.lower() in ("false", "0"):
                inbox_notices = inbox_notices.filter(is_saved=False)
            else:
                return Response(
                    {"detail": "saved must be true or false"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = InboxNoticeSerializer(inbox_notices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InboxNoticeDetailView(APIView):
    @extend_schema(
        summary="공지 상세 조회",
        description="로그인한 사용자의 inbox 공지 상세를 조회합니다.",
        responses={200: InboxNoticeSerializer, 401: "Unauthorized", 404: "Not Found"},
    )
    def get(self, request, inbox_notice_id):
        author = request.user

        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        inbox_notice = get_object_or_404(
            InboxNotice.objects.select_related("notice_id", "notice_id__source_id"),
            id=inbox_notice_id,
            user_id=author,
        )
        serializer = InboxNoticeSerializer(inbox_notice)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InboxNoticeSaveView(APIView):
    @extend_schema(
        summary="공지 저장 상태 변경",
        description="로그인한 사용자의 inbox 공지를 저장하거나 저장 해제합니다.",
        request=InboxNoticeSaveSerializer,
        responses={
            200: InboxNoticeSerializer,
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
        },
    )
    def patch(self, request, inbox_notice_id):
        author = request.user

        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        inbox_notice = get_object_or_404(
            InboxNotice.objects.select_related("notice_id", "notice_id__source_id"),
            id=inbox_notice_id,
            user_id=author,
        )

        request_serializer = InboxNoticeSaveSerializer(data=request.data)
        if request_serializer.is_valid(raise_exception=True):
            inbox_notice.is_saved = request_serializer.validated_data["is_saved"]
            inbox_notice.save(update_fields=["is_saved"])

        response_serializer = InboxNoticeSerializer(inbox_notice)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
