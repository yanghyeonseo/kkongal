from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, extend_schema

from account.models import Interest
from sources.models import SourceSubscription

from .models import InboxNotice, Notice
from .serializers import (
    AiInboxNoticeCreateSerializer,
    AiNoticeCandidateSerializer,
    InboxNoticeReadSerializer,
    InboxNoticeSaveSerializer,
    InboxNoticeSerializer,
    NoticeSerializer,
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

        request_serializer = InboxNoticeReadSerializer(data=request.data)
        if request_serializer.is_valid(raise_exception=True):
            inbox_notice.is_read = request_serializer.validated_data["is_read"]
            inbox_notice.save(update_fields=["is_read"])

        response_serializer = InboxNoticeSerializer(inbox_notice)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class AiNoticeListView(APIView):
    # 내부 파이프라인/서비스 전용. 익명 접근 시 유저 PII/공지 열람을 막기 위해 admin(staff) 한정.
    # (실제 선별은 ai.service 가 ORM 으로 직접 수행 — 이 HTTP 엔드포인트는 외부 워커용.)
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="AI 분석용 공지 목록 조회",
        description="크롤링되어 저장된 공지 목록을 AI 분석용으로 조회합니다.",
        parameters=[
            OpenApiParameter(
                name="source_id",
                description="특정 출처 사이트의 공지만 조회합니다.",
                required=False,
                type=int,
            )
        ],
        responses={200: NoticeSerializer(many=True)},
    )
    def get(self, request):
        notices = Notice.objects.select_related("source_id").order_by(
            "-published_at", "-created_at", "-id"
        )

        source_id = request.query_params.get("source_id")
        if source_id:
            notices = notices.filter(source_id_id=source_id)

        serializer = NoticeSerializer(notices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AiNoticeCandidateListView(APIView):
    # 구독자 이메일/프로필(PII)을 반환하므로 admin(staff) 한정. (C1 대응)
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="AI 분석용 후보 유저/관심사 조회",
        description="공지의 출처 사이트를 구독한 사용자와 각 사용자의 관심사를 조회합니다.",
        responses={
            200: AiNoticeCandidateSerializer(many=True),
            404: "Not Found",
        },
    )
    def get(self, request, notice_id):
        notice = get_object_or_404(Notice, id=notice_id)
        subscriptions = (
            SourceSubscription.objects.filter(source_id=notice.source_id)
            .select_related("user_id")
            .prefetch_related(
                Prefetch(
                    "user_id__interests",
                    queryset=Interest.objects.order_by("-priority", "-created_at"),
                )
            )
            .order_by("user_id__id")
        )

        candidates = []
        for subscription in subscriptions:
            user = subscription.user_id
            candidates.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "age": user.age,
                    "job": user.job,
                    "gender": user.gender,
                    "interests": [
                        {
                            "id": interest.id,
                            "keyword": interest.keyword,
                            "description": interest.description,
                            "priority": interest.priority,
                        }
                        for interest in user.interests.all()
                    ],
                }
            )

        serializer = AiNoticeCandidateSerializer(candidates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AiInboxNoticeCreateView(APIView):
    # 임의 user_id 로 타인 inbox 에 쓰기가 가능하므로(알림 주입 위험) admin(staff) 한정. (C2 대응)
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="AI 분석 결과 inbox 저장",
        description="AI가 분석한 사용자별 공지 매칭 결과를 inbox_notice에 생성하거나 업데이트합니다.",
        request=AiInboxNoticeCreateSerializer,
        responses={
            200: InboxNoticeSerializer,
            201: InboxNoticeSerializer,
            400: "Bad Request",
        },
    )
    def post(self, request):
        is_many = isinstance(request.data, list)
        request_serializer = AiInboxNoticeCreateSerializer(
            data=request.data, many=is_many
        )
        request_serializer.is_valid(raise_exception=True)

        validated_items = (
            request_serializer.validated_data
            if is_many
            else [request_serializer.validated_data]
        )

        inbox_notices = []
        created_count = 0
        with transaction.atomic():
            for item in validated_items:
                inbox_notice, created = InboxNotice.objects.update_or_create(
                    user_id=item["user"],
                    notice_id=item["notice"],
                    defaults={
                        "relevance_score": item["relevance_score"],
                        "matched_keywords": item["matched_keywords"],
                        "reason": item["reason"],
                    },
                )
                inbox_notices.append(inbox_notice)
                if created:
                    created_count += 1

        response_serializer = InboxNoticeSerializer(inbox_notices, many=True)
        response_status = (
            status.HTTP_201_CREATED if created_count > 0 else status.HTTP_200_OK
        )

        if is_many:
            return Response(response_serializer.data, status=response_status)
        return Response(response_serializer.data[0], status=response_status)
