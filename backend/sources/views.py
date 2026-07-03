import logging
import threading
from datetime import timedelta

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
from .naming import favicon_url_for, friendly_name_for
from .serializers import (
    NoticeSourceNameUpdateSerializer,
    NoticeSourceSerializer,
    SourceSubscriptionCreateSerializer,
    SourceSubscriptionSerializer,
)

log = logging.getLogger("sources")

# 이 시간 안에 다시 sync 를 눌러도 실제 크롤은 생략하고, 기존 미분류 공지만 이 사용자에
# 대해 재선별한다(사이트 부하·크롤 비용 보호).
_SYNC_RATE_LIMIT_SECONDS = 30
# 한 번의 동기화에서 AI 선별로 넘길 공지 최대 수(LLM 비용 상한).
_SYNC_CLASSIFY_CAP = 10
# 온디맨드 스크랩 창: 최근 N일 이내 공지를 최대 M건까지 가져온다.
_SYNC_RECENT_DAYS = 7
_SYNC_FETCH_CAP = 20
_UNSUPPORTED_MESSAGE = "이 사이트는 자동 수집을 지원하지 않아요."


def _dispatch_alerts_async(user) -> threading.Thread:
    """이 사용자의 새 추천 공지 알림을 백그라운드(데몬 스레드)에서 논블로킹 발송한다.

    온디맨드 동기화 응답이 SMTP 왕복(느리거나 멈출 수 있음)을 기다리며 무한 로딩되지
    않도록, 실제 발송은 별도 스레드에 맡기고 즉시 반환한다(원래의 '무한 로딩' 버그
    방지). 결과는 서버 로그로만 남는다(best-effort). DB 커넥션은 스레드 로컬이므로
    작업 후 ``finally`` 에서 이 스레드가 연 커넥션을 반드시 닫는다.
    """

    def _run():
        # 지연 import(순환 방지): alert → notices/ai 방향 의존을 뷰 로드시로 미룬다.
        from alert.service import dispatch_pending

        try:
            dispatch_pending(user=user)
        except Exception:  # noqa: BLE001 - 백그라운드 스레드가 조용히 죽지 않도록 방어
            log.exception("동기화 후 알림 발송 실패 (user=%s)", getattr(user, "id", None))
        finally:
            from django.db import connection

            connection.close()

    thread = threading.Thread(
        target=_run,
        name=f"sync-dispatch-{getattr(user, 'id', 'anon')}",
        daemon=True,
    )
    thread.start()
    return thread


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
        config = load_config()
        source, _source_created = NoticeSource.objects.get_or_create(
            url=url,
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
                "favicon_url": favicon_url_for(site.url),
                "source_id": source_id_by_url.get(site.url),
                "subscribed": source_id_by_url.get(site.url)
                in subscribed_source_ids,
            }
            for site in sites
        ]
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
        summary="사이트 온디맨드 동기화",
        description=(
            "구독한 사이트에서 최근 7일 이내 공지를 최대 20건 스크랩하고, 그중 가장 최근 "
            "10건을 요청 사용자에 대해 AI 선별합니다. 신규 공지는 저장 시 공지당 1회 "
            "보강(enrich)합니다. 최근 30초 내 크롤 이력이 있으면 재크롤 없이 기존 공지만 "
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
            # 크롤 전 기존 공지 id 스냅샷 → 이후 '이번에 새로 생긴' 공지만 골라 보강한다.
            pre_ids = set(
                Notice.objects.filter(source_id=source).values_list("id", flat=True)
            )
            try:
                report = self._crawl_recent(config, site)
            except Exception:  # 방어: 어떤 경우에도 500 대신 graceful 200.
                log.exception("sync 크롤 실패 (source=%s)", source.id)
                crawl_failed = True
            else:
                fetched = report.fetched
                new_notices = report.inserted
                # crawl 은 스크래이핑 예외를 report.errors 로 삼킨다. 아무것도 못
                # 가져오고 에러만 있으면 라이브 사이트 장애로 보고 graceful 처리한다.
                if report.errors and report.fetched == 0:
                    crawl_failed = True
                else:
                    crawled = True

            # 이번에 새로 저장된 공지에 한해 공지당 1회 보강(있으면).
            if crawled and new_notices:
                newly = Notice.objects.filter(source_id=source).exclude(
                    id__in=pre_ids
                )
                self._enrich_new_notices(newly)

        # 이 source 의 가장 최근 공지 최대 10건을 요청 사용자에 대해서만 선별(비용 최소화).
        recent_notices = self._notices_to_classify(source)
        summary = classify_notices_for_user(user, recent_notices)
        # 저장은 store-all(비추천 포함)이지만, 사용자에게 보여줄/알릴 '새 공지'는 추천분만.
        inbox_added = int(summary.get("recommended", 0))

        # 새로 추천된 공지가 있으면 이 사용자의 알림을 논블로킹으로 발송한다. SMTP 왕복이
        # HTTP 응답을 막지 않도록 백그라운드 스레드에 맡긴다(무한 로딩 버그 방지).
        if inbox_added > 0:
            _dispatch_alerts_async(user)

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

    @staticmethod
    def _crawl_recent(config, site):
        """최근 7일 이내 공지를 최대 20건 스크랩한다.

        순진한 매처는 OFF(match_inbox=False) — inbox 편입은 뒤이은 AI 선별만 담당한다.
        """
        repository = DjangoNoticeRepository(config=config, match_inbox=False)
        service = NoticeCrawlService(config=config, repository=repository)
        return service.crawl_recent(
            site.id, days=_SYNC_RECENT_DAYS, limit=_SYNC_FETCH_CAP
        )

    @staticmethod
    def _enrich_new_notices(notices):
        """신규 공지에 공지당 1회 보강 적용. ai.enrich 미배포/실패는 조용히 건너뛴다."""
        notices = list(notices)
        if not notices:
            return
        try:
            from ai.enrich import enrich_notices  # 지연 import(미배포/순환 방어).
        except Exception:
            log.debug("ai.enrich 미배포 — 보강 건너뜀 (count=%d)", len(notices))
            return
        try:
            enrich_notices(notices)
        except Exception:  # 보강 실패가 동기화 자체를 막지 않도록 삼킨다.
            log.exception("공지 보강 실패 (count=%d)", len(notices))

    def _notices_to_classify(self, source):
        """이 source 공지 중 가장 최근 10건(게시일 우선, 없으면 생성일)."""
        return list(
            Notice.objects.filter(source_id=source)
            .annotate(effective_at=Coalesce("published_at", "created_at"))
            .order_by("-effective_at", "-id")[:_SYNC_CLASSIFY_CAP]
        )

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
