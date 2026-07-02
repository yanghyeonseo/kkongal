import logging
from datetime import timedelta
from urllib.parse import urlparse

from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from ai.service import classify_notices_for_user
from crawler.config_loader import load_config
from crawler.repository import DjangoNoticeRepository
from crawler.service import NoticeCrawlService
from notices.models import Notice

from .models import NoticeSource, SourceSubscription
from .serializers import (
    SourceSubscriptionCreateSerializer,
    SourceSubscriptionSerializer,
)

log = logging.getLogger("sources")

# 이 시간 안에 다시 sync 를 눌러도 실제 크롤은 생략하고, 기존 미분류 공지만 이 사용자에
# 대해 재선별한다(사이트 부하·크롤 비용 보호).
_SYNC_RATE_LIMIT_SECONDS = 30
# 한 번의 동기화에서 AI 선별로 넘길 공지 최대 수(LLM 비용 상한).
_SYNC_CLASSIFY_CAP = 10
# '최근 공지' 판단 창(시간).
_SYNC_RECENT_HOURS = 24
_UNSUPPORTED_MESSAGE = "이 사이트는 자동 수집을 지원하지 않아요."


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


class SourceCatalogView(APIView):
    @extend_schema(
        summary="지원 사이트 카탈로그",
        description=(
            "자동 수집(크롤러)이 지원하는 사이트 목록을 반환합니다. 등록 UI 는 이 "
            "카탈로그에서 사이트를 고릅니다. 인증 시 현재 사용자의 구독 여부와 "
            "NoticeSource id 를 함께 표시합니다."
        ),
        responses={
            200: "[{name, url, category, subscribed: bool, source_id: int|null}]"
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
                "source_id": source_id_by_url.get(site.url),
                "subscribed": source_id_by_url.get(site.url)
                in subscribed_source_ids,
            }
            for site in sites
        ]
        return Response(catalog, status=status.HTTP_200_OK)


class SourceSyncView(APIView):
    @extend_schema(
        summary="사이트 온디맨드 동기화",
        description=(
            "구독한 사이트를 즉시 크롤링하고 최근 공지(최대 10건)를 요청 사용자에 대해 "
            "AI 선별합니다. 최근 30초 내 크롤 이력이 있으면 재크롤 없이 기존 미분류 공지만 "
            "재선별하고, 자동 수집 미지원 사이트는 400 을 반환합니다. 라이브 사이트 장애 "
            "시에도 500 대신 crawled=false 와 안내 메시지를 담아 200 으로 응답합니다."
        ),
        request=None,
        responses={
            200: "{crawled: bool, fetched: int, new_notices: int, inbox_added: int, message: str}",
            400: "자동 수집 미지원",
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

        # 구독한 사이트만 동기화할 수 있다.
        if not SourceSubscription.objects.filter(
            user_id=user, source_id=source
        ).exists():
            return Response(
                {"detail": "구독한 사이트만 동기화할 수 있어요."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # source.url → config 사이트 매핑. 없으면 자동 수집 미지원.
        config = load_config()
        site = next((s for s in config.sites if s.url == source.url), None)
        if site is None:
            return Response(
                {"detail": _UNSUPPORTED_MESSAGE},
                status=status.HTTP_400_BAD_REQUEST,
            )

        crawled = False
        crawl_failed = False
        fetched = 0
        new_notices = 0

        rate_limited = source.crawled_at is not None and (
            timezone.now() - source.crawled_at
        ) < timedelta(seconds=_SYNC_RATE_LIMIT_SECONDS)

        if not rate_limited:
            # 순진한 매처는 OFF(match_inbox=False) — inbox 편입은 AI 선별만 담당.
            try:
                repository = DjangoNoticeRepository(
                    config=config, match_inbox=False
                )
                service = NoticeCrawlService(
                    config=config, repository=repository
                )
                report = service.crawl_site(site.id)
                fetched = report.fetched
                new_notices = report.inserted
                # crawl_site 는 스크래이핑 예외를 report.errors 로 삼킨다. 아무것도 못
                # 가져오고 에러만 있으면 라이브 사이트 장애로 보고 graceful 처리한다.
                if report.errors and report.fetched == 0:
                    crawl_failed = True
                else:
                    crawled = True
            except Exception:  # 방어: 어떤 경우에도 500 대신 graceful 200.
                log.exception("sync 크롤 실패 (source=%s)", source.id)
                crawl_failed = True

        # 이 source 의 최근 공지 최대 10건을 요청 사용자에 대해서만 선별(비용 최소화).
        recent_notices = self._notices_to_classify(source)
        summary = classify_notices_for_user(user, recent_notices)
        inbox_added = int(summary.get("created", 0))

        message = self._build_message(
            rate_limited=rate_limited,
            crawl_failed=crawl_failed,
            inbox_added=inbox_added,
        )

        return Response(
            {
                "crawled": crawled,
                "fetched": fetched,
                "new_notices": new_notices,
                "inbox_added": inbox_added,
                "message": message,
            },
            status=status.HTTP_200_OK,
        )

    def _notices_to_classify(self, source):
        """이 source 공지 중 24h 이내 최신순 ≤10건. 없으면 최신 ≤10건으로 폴백."""
        base = (
            Notice.objects.filter(source_id=source)
            .annotate(effective_at=Coalesce("published_at", "created_at"))
            .order_by("-effective_at", "-id")
        )
        cutoff = timezone.now() - timedelta(hours=_SYNC_RECENT_HOURS)
        recent = list(base.filter(effective_at__gte=cutoff)[:_SYNC_CLASSIFY_CAP])
        if not recent:
            recent = list(base[:_SYNC_CLASSIFY_CAP])
        return recent

    @staticmethod
    def _build_message(*, rate_limited, crawl_failed, inbox_added):
        if crawl_failed:
            base = "지금은 사이트에서 공지를 가져오지 못했어요. 잠시 후 다시 시도해 주세요."
        elif rate_limited:
            base = "방금 동기화해서 기존 공지만 다시 확인했어요."
        else:
            base = "동기화를 완료했어요."
        if inbox_added:
            return f"{base} 관심 있을 만한 공지 {inbox_added}건을 새로 담았어요."
        if crawl_failed:
            return base
        return f"{base} 새로 추천할 공지는 없었어요."
