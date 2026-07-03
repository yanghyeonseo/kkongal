from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, extend_schema

from ai.status import get_status

from .models import InboxNotice
from .serializers import (
    InboxNoticeReadSerializer,
    InboxNoticeSaveSerializer,
    InboxNoticeSerializer,
)


def _require_login(request):
    """Return a 401 Response when the request is unauthenticated, else None.

    Inbox views run under the project-wide AllowAny default, so each one gates
    on the authenticated user itself and returns this shared payload.
    """
    if request.user.is_authenticated:
        return None
    return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)


def _get_user_inbox_notice(user, inbox_notice_id):
    return get_object_or_404(
        InboxNotice.objects.select_related("notice_id", "notice_id__source_id"),
        id=inbox_notice_id,
        user_id=user,
    )


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
            ),
            OpenApiParameter(
                name="recommended",
                description="true이면 AI 추천(is_recommended) 공지만, false이면 비추천 공지만 조회합니다.",
                required=False,
                type=bool,
            ),
        ],
        responses={200: InboxNoticeSerializer(many=True), 401: "Unauthorized"},
    )
    def get(self, request):
        denied = _require_login(request)
        if denied:
            return denied

        inbox_notices = (
            InboxNotice.objects.filter(user_id=request.user)
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

        recommended = request.query_params.get("recommended")
        if recommended is not None:
            if recommended.lower() in ("true", "1"):
                inbox_notices = inbox_notices.filter(is_recommended=True)
            elif recommended.lower() in ("false", "0"):
                inbox_notices = inbox_notices.filter(is_recommended=False)
            else:
                return Response(
                    {"detail": "recommended must be true or false"},
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
        denied = _require_login(request)
        if denied:
            return denied

        inbox_notice = _get_user_inbox_notice(request.user, inbox_notice_id)
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
        denied = _require_login(request)
        if denied:
            return denied

        inbox_notice = _get_user_inbox_notice(request.user, inbox_notice_id)

        request_serializer = InboxNoticeSaveSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        inbox_notice.is_saved = request_serializer.validated_data["is_saved"]
        inbox_notice.save(update_fields=["is_saved"])

        response_serializer = InboxNoticeSerializer(inbox_notice)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class InboxNoticeReadView(APIView):
    @extend_schema(
        summary="공지 읽음 상태 변경",
        description="로그인한 사용자의 inbox 공지를 읽음(기본) 또는 안읽음으로 표시합니다.",
        request=InboxNoticeReadSerializer,
        responses={
            200: InboxNoticeSerializer,
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
        },
    )
    def patch(self, request, inbox_notice_id):
        denied = _require_login(request)
        if denied:
            return denied

        inbox_notice = _get_user_inbox_notice(request.user, inbox_notice_id)

        request_serializer = InboxNoticeReadSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        inbox_notice.is_read = request_serializer.validated_data["is_read"]
        inbox_notice.save(update_fields=["is_read"])

        response_serializer = InboxNoticeSerializer(inbox_notice)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class AiStatusView(APIView):
    # 프론트 배너용 AI 가용 상태 — 민감정보가 없어 인증 없이 공개한다.
    permission_classes = [AllowAny]

    @extend_schema(
        summary="AI 가용 상태 조회",
        description="AI 선별의 현재 상태를 반환합니다. degraded=true 면 키워드 기반 폴백 동작 중.",
        responses={200: dict},
    )
    def get(self, request):
        return Response(get_status(), status=status.HTTP_200_OK)
