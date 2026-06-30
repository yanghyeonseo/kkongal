from django.shortcuts import get_object_or_404
from urllib.parse import urlparse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import NoticeSource, SourceSubscription
from .serializers import (
    SourceSubscriptionCreateSerializer,
    SourceSubscriptionSerializer,
)


class SourceSubscriptionListView(APIView):
    @extend_schema(
        summary="등록 사이트 목록 조회",
        description="로그인한 사용자가 등록한 공지 사이트 목록을 조회합니다.",
        responses={200: SourceSubscriptionSerializer(many=True), 401: "Unauthorized"},
    )
    def get(self, request):
        author = request.user

        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        subscriptions = (
            SourceSubscription.objects.filter(user_id=author)
            .select_related("source_id")
            .order_by("source_id__name")
        )
        serializer = SourceSubscriptionSerializer(subscriptions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="사이트 등록",
        description="새로운 url을 로그인한 사용자의 등록 사이트로 추가합니다.",
        request=SourceSubscriptionCreateSerializer,
        responses={
            200: SourceSubscriptionSerializer,
            201: SourceSubscriptionSerializer,
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

        serializer = SourceSubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # parsed_url = urlparse(validated_data["url"])
        # source_name = parsed_url.netloc or validated_data["url"]

        source, source_created = NoticeSource.objects.get_or_create(
            url=validated_data["url"],
            # defaults={"name": source_name},
        )

        subscription, subscription_created = SourceSubscription.objects.get_or_create(
            user_id=author,
            source_id=source,
        )
        response_status = (
            status.HTTP_201_CREATED if subscription_created else status.HTTP_200_OK
        )
        return Response(
            SourceSubscriptionSerializer(subscription).data,
            status=response_status,
        )


class SourceSubscriptionDetailView(APIView):
    @extend_schema(
        summary="등록 사이트 삭제",
        description="로그인한 사용자의 등록 사이트를 삭제합니다.",
        responses={204: "No Content", 401: "Unauthorized", 404: "Not Found"},
    )
    def delete(self, request, subscription_id):
        author = request.user

        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        subscription = get_object_or_404(
            SourceSubscription,
            id=subscription_id,
            user_id=author,
        )
        subscription.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
