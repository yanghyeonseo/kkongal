import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from crawler.config_loader import load_config

from . import sync_jobs
from .models import NoticeSource, SourceSubscription
from .naming import favicon_url_for, friendly_name_for
from .url_normalize import normalize_url
from .serializers import (
    NoticeSourceNameUpdateSerializer,
    NoticeSourceSerializer,
    SourceSubscriptionCreateSerializer,
    SourceSubscriptionSerializer,
)

log = logging.getLogger("sources")


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
        url = serializer.validated_data["url"]

        # 표시명/파비콘은 URL 만으로 결정한다(사이트를 직접 받지 않아 등록이 빠르고 안전).
        # 정규화 URL 로 dedup 하므로 표기만 다른 같은 게시판은 하나의 소스로 합쳐지고,
        # 먼저 학습된 크롤 레시피를 이 구독자가 그대로 재사용한다.
        config = load_config()
        source, _source_created = NoticeSource.resolve(
            url,
            defaults={
                "name": friendly_name_for(url, config),
                "favicon_url": favicon_url_for(url),
            },
        )
        # 크롤러가 먼저 만든 source 는 표시명/파비콘이 비어 있을 수 있다 → 등록 시 채운다.
        self._backfill_source(source, config)

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

    @staticmethod
    def _backfill_source(source, config):
        """빈 표시명/파비콘을 URL 기반으로 채운다(네트워크 없음). 바뀐 것만 저장."""
        updates = {}
        if not source.name:
            updates["name"] = friendly_name_for(source.url, config)
        if not source.favicon_url:
            updates["favicon_url"] = favicon_url_for(source.url)
        if updates:
            for field, value in updates.items():
                setattr(source, field, value)
            source.save(update_fields=list(updates))


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


class SourceCatalogView(APIView):
    # 카탈로그는 비로그인도 열람 가능(로그인 시 구독 여부를 추가로 표시). 공개 엔드포인트.
    permission_classes = [AllowAny]

    @extend_schema(
        summary="지원 사이트 카탈로그",
        description=(
            "자동 수집(크롤러)이 지원하는 사이트 목록을 반환합니다. 등록 UI 는 이 "
            "카탈로그에서 사이트를 고릅니다. 내장(config) 사이트뿐 아니라, 크롤 "
            "레시피가 확정된(scraper_kind 존재) 사용자 등록 커스텀 사이트도 함께 "
            "노출해 다른 사용자가 재사용할 수 있게 합니다(레시피 미확정 사이트는 "
            "깨진/파싱 불가 URL 노출을 막기 위해 제외). 내장 사이트와 같은 게시판을 "
            "가리키는(normalized_url 동일) 커스텀 사이트는 내장 항목이 우선하며 "
            "중복 노출되지 않습니다. 인증 시 현재 사용자의 구독 여부와 NoticeSource "
            "id 를 함께 표시합니다."
        ),
        responses={
            200: (
                "[{name, url, category, favicon_url, source_id: int|null, "
                "subscribed: bool, custom: bool}]"
            )
        },
    )
    def get(self, request):
        config = load_config()
        sites = list(config.enabled_sites())

        # config url → 이미 존재하는 NoticeSource id 매핑(있으면 노출).
        source_id_by_url = dict(
            NoticeSource.objects.filter(
                url__in=[site.url for site in sites]
            ).values_list("url", "id")
        )

        # 내장 사이트들의 정규화 URL 집합 — 같은 게시판을 가리키는 커스텀 사이트를
        # 중복 노출하지 않기 위한 제외 기준(내장이 우선).
        builtin_normalized_urls = {normalize_url(site.url) for site in sites}

        # 크롤 레시피가 확정된(is_recipe_confirmed) 커스텀 사이트만 카탈로그에 노출한다
        # (미확정 사이트는 깨진/파싱 불가 URL 일 수 있어 제외). 내장 사이트와 같은
        # 게시판(normalized_url 동일)은 내장이 이미 노출하므로 제외.
        custom_sources = list(
            NoticeSource.objects.exclude(scraper_kind="").exclude(
                normalized_url__in=builtin_normalized_urls
            )
        )

        subscribed_source_ids: set[int] = set()
        if request.user.is_authenticated:
            subscribed_source_ids = set(
                SourceSubscription.objects.filter(
                    user_id=request.user
                ).values_list("source_id_id", flat=True)
            )

        catalog = [
            {
                "name": site.name,
                "url": site.url,
                "category": site.category,
                "favicon_url": favicon_url_for(site.url),
                "source_id": source_id_by_url.get(site.url),
                "subscribed": source_id_by_url.get(site.url)
                in subscribed_source_ids,
                "custom": False,
            }
            for site in sites
        ]
        catalog.extend(
            {
                "name": source.name,
                "url": source.url,
                "category": source.category,
                "favicon_url": source.favicon_url,
                "source_id": source.id,
                "subscribed": source.id in subscribed_source_ids,
                "custom": True,
            }
            for source in custom_sources
        )
        return Response(catalog, status=status.HTTP_200_OK)


class SourceDetailView(APIView):
    @extend_schema(
        summary="사이트 표시명 편집",
        description=(
            "구독한 사이트의 사람이 읽는 표시명(name)을 변경합니다. 인증 및 해당 "
            "사이트 구독이 필요하며, name 은 비어 있지 않고 128자 이하여야 합니다. "
            "갱신된 사이트를 반환합니다."
        ),
        request=NoticeSourceNameUpdateSerializer,
        responses={
            200: NoticeSourceSerializer,
            400: "Bad Request",
            401: "Unauthorized",
            403: "구독자가 아님",
            404: "Not Found",
        },
    )
    def patch(self, request, source_id):
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        source = get_object_or_404(NoticeSource, id=source_id)

        if not SourceSubscription.objects.filter(
            user_id=user, source_id=source
        ).exists():
            return Response(
                {"detail": "구독한 사이트만 편집할 수 있어요."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = NoticeSourceNameUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        source.name = serializer.validated_data["name"]
        source.save(update_fields=["name"])
        return Response(
            NoticeSourceSerializer(source).data, status=status.HTTP_200_OK
        )


class SourceSyncView(APIView):
    @extend_schema(
        summary="사이트 온디맨드 동기화(비동기 시작)",
        description=(
            "구독한 사이트의 동기화를 백그라운드 작업으로 시작하고 즉시 반환합니다. "
            "실제 크롤·공지당 1회 보강·AI 선별·알림 발송은 단일 순차 워커가 사이트를 "
            "하나씩 처리하며, 진행/완료는 GET /api/sources/sync/status/ 로 폴링합니다. "
            "카탈로그 사이트는 전용 손파서로, 그 외 임의 사이트는 generic 파이프라인"
            "(rss→json_api→heuristic→llm)으로 자동 수집합니다."
        ),
        request=None,
        responses={
            200: '{"status": "started", "source_id": int}',
            401: "Unauthorized",
            403: "구독자가 아님",
            404: "Not Found",
        },
    )
    def post(self, request, source_id):
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        source = get_object_or_404(NoticeSource, id=source_id)

        if not SourceSubscription.objects.filter(
            user_id=user, source_id=source
        ).exists():
            return Response(
                {"detail": "구독한 사이트만 동기화할 수 있어요."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 카탈로그 사이트(builtin 손파서)든 임의 사이트(generic 파이프라인)든 모두 동기화
        # 대상이다. 워커가 source.url 의 카탈로그 매핑 유무에 따라 알아서 경로를 고른다.
        # 실제 작업(크롤→보강→선별→발송)은 순차 워커에 맡기고 즉시 반환한다. LLM 스로틀
        # 때문에 인라인으로 하면 응답이 멈출 수 있어, 워커가 사이트를 하나씩 처리한다.
        sync_jobs.enqueue(user, source)
        return Response(
            {"status": "started", "source_id": source.id},
            status=status.HTTP_200_OK,
        )


class SourceSyncStatusView(APIView):
    @extend_schema(
        summary="동기화 진행 상태 조회",
        description=(
            "요청 사용자가 구독한 사이트들의 동기화 작업 상태를 반환합니다. 상태가 "
            "없는(idle) 사이트는 생략됩니다. 프런트는 이 엔드포인트를 폴링해 사이트별 "
            "running→done/failed 전이를 감지합니다."
        ),
        responses={
            200: (
                '{"jobs": {"<source_id>": {"status": "running|done|failed", '
                '"inbox_added": int, "message": str}}}'
            ),
            401: "Unauthorized",
        },
    )
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        source_ids = list(
            SourceSubscription.objects.filter(user_id=user).values_list(
                "source_id_id", flat=True
            )
        )
        jobs = sync_jobs.get_status_for(user, source_ids)
        return Response({"jobs": jobs}, status=status.HTTP_200_OK)
