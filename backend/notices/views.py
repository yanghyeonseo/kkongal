from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import InboxNotice
from .serializers import InboxNoticeSerializer


class InboxNoticeListView(APIView):
    @extend_schema(
        summary="공지 목록 조회",
        description="로그인한 사용자의 inbox 공지 목록을 조회합니다.",
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
