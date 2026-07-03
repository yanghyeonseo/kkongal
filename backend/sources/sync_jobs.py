"""온디맨드 동기화의 인프로세스 순차 작업 러너 + 캐시 기반 상태.

동기화 뷰(SourceSyncView)는 동기 검증만 하고 실제 작업(크롤→보강→선별→발송)은
여기에 enqueue 한다. 단일 데몬 워커 스레드가 작업을 하나씩 순차 처리하므로:
  - LLM 클라이언트가 요청을 ~4.5s 에 1회로 스로틀해도 HTTP 응답은 막히지 않고,
  - 사이트가 한 건씩 끝나 프런트가 완료를 하나씩 보여줄 수 있다(깔끔한 per-site 완료).

상태는 Django 캐시에 ``sync:job:{user_id}:{source_id}`` 키로 남긴다. 프런트는
상태 엔드포인트를 폴링해 running→done/failed 전이를 감지한다. 캐시 유틸은 절대
호출자에게 예외를 전파하지 않는다(best-effort). TTL 로 stale 'running' 은 만료된다.

주의(운영): 기본 설정은 프로세스 로컬 LocMemCache 이므로 워커/폴링이 같은 프로세스
안에 있을 때만 상태를 공유한다(개발 runserver 단일 프로세스에서는 문제없음). 다중
프로세스 배포에서는 공유 캐시(Redis/DB)가 필요하다.
"""
from __future__ import annotations

import logging
import queue
import threading
from datetime import timedelta

from django.core.cache import cache
from django.db.models.functions import Coalesce
from django.utils import timezone

from ai.service import classify_notices_for_user
from crawler.repository import DjangoNoticeRepository
from crawler.service import NoticeCrawlService
from notices.models import Notice

from .models import NoticeSource

log = logging.getLogger("sources")

# 이 시간 안에 다시 sync 를 눌러도 실제 크롤은 생략하고, 기존 미분류 공지만 이 사용자에
# 대해 재선별한다(사이트 부하·크롤 비용 보호).
_SYNC_RATE_LIMIT_SECONDS = 30
# 한 번의 동기화에서 AI 선별로 넘길 공지 최대 수(LLM 비용 상한).
_SYNC_CLASSIFY_CAP = 10
# 온디맨드 스크랩 창: 최근 N일 이내 공지를 최대 M건까지 가져온다.
_SYNC_RECENT_DAYS = 7
_SYNC_FETCH_CAP = 20

# 캐시 상태 TTL(초). 워커가 어떤 이유로 종료해 terminal 상태를 못 남겨도, stale
# 'running' 은 이 시간 뒤 만료되어 idle(=엔트리 없음) 로 취급된다.
_STATUS_TTL_SECONDS = 600


# ---------------------------------------------------------------------------
# 캐시 상태(best-effort — 절대 raise 하지 않는다)
# ---------------------------------------------------------------------------
def _status_key(user_id: int, source_id: int) -> str:
    return f"sync:job:{user_id}:{source_id}"


def _set_status(user_id, source_id, status, *, inbox_added=0, message="") -> None:
    entry = {"status": status, "inbox_added": int(inbox_added), "message": message}
    try:
        cache.set(_status_key(user_id, source_id), entry, _STATUS_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - 상태 기록 실패가 동기화를 막지 않도록 방어
        log.exception("sync 상태 기록 실패 (user=%s source=%s)", user_id, source_id)


def get_status_for(user, source_ids) -> dict:
    """요청 사용자의 (구독) source id 들에 대한 캐시 상태를 모은다.

    엔트리가 없는(=idle) id 는 결과에서 생략한다. 절대 raise 하지 않는다.
    """
    result: dict = {}
    for source_id in source_ids:
        try:
            entry = cache.get(_status_key(user.id, source_id))
        except Exception:  # noqa: BLE001
            entry = None
        if entry:
            result[source_id] = entry
    return result


# ---------------------------------------------------------------------------
# 동기화 실제 작업(뷰에서 옮겨온 크롤→보강→선별→발송 로직)
# ---------------------------------------------------------------------------
def run_sync_for_source(user, source, config) -> dict:
    """한 사용자·한 사이트의 동기화를 순차(블로킹)로 수행하고 요약을 반환한다.

    워커 스레드에서 호출된다(이미 백그라운드이므로 발송도 여기서 동기로 한다).
    최근 30초 내 크롤 이력이 있으면 재크롤 없이 기존 공지만 재선별한다. 라이브
    사이트 장애 시에도 예외를 던지지 않고 crawled=False + 안내 메시지로 요약한다.
    """
    # site 가 있으면 카탈로그 손파서(builtin), 없으면 generic 파이프라인(임의 사이트).
    site = next((s for s in config.sites if s.url == source.url), None)

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
            report = _crawl_recent(config, site, source)
        except Exception:  # 방어: 어떤 경우에도 예외 대신 graceful 요약.
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
            newly = Notice.objects.filter(source_id=source).exclude(id__in=pre_ids)
            _enrich_new_notices(newly)

    # 이 source 의 가장 최근 공지 최대 10건을 요청 사용자에 대해서만 선별(비용 최소화).
    recent_notices = _notices_to_classify(source)
    summary = classify_notices_for_user(user, recent_notices)
    # 저장은 store-all(비추천 포함)이지만, 사용자에게 보여줄/알릴 '새 공지'는 추천분만.
    inbox_added = int(summary.get("recommended", 0))

    # 새로 추천된 공지가 있으면 이 사용자의 알림을 발송한다. 워커가 이미 백그라운드
    # 스레드이므로 여기서는 동기로 호출한다(HTTP 응답을 막지 않음).
    if inbox_added > 0:
        _dispatch_alerts(user)

    message = _build_message(
        rate_limited=rate_limited,
        crawl_failed=crawl_failed,
        inbox_added=inbox_added,
    )
    return {
        "crawled": crawled,
        "fetched": fetched,
        "new_notices": new_notices,
        "inbox_added": inbox_added,
        "message": message,
    }


def _dispatch_alerts(user) -> None:
    """이 사용자의 새 추천 공지 알림을 발송한다(워커 스레드 내 동기 호출).

    발송 실패가 동기화 작업 자체를 실패로 만들지 않도록 삼킨다(best-effort, 로그만).
    """
    # 지연 import(순환 방지): alert → notices/ai 방향 의존을 호출 시점으로 미룬다.
    from alert.service import dispatch_pending

    try:
        dispatch_pending(user=user)
    except Exception:  # noqa: BLE001 - 발송 실패가 동기화를 실패로 만들지 않도록 방어
        log.exception("동기화 후 알림 발송 실패 (user=%s)", getattr(user, "id", None))


def _crawl_recent(config, site, source):
    """최근 7일 이내 공지를 최대 20건 스크랩한다.

    site 가 있으면 카탈로그 손파서(builtin), 없으면 등록된 NoticeSource 를 generic
    파이프라인으로 크롤한다(임의 사이트). 어느 쪽이든 순진한 매처는 OFF(match_inbox=False)
    — inbox 편입은 뒤이은 AI 선별만 담당한다.
    """
    if site is not None:
        repository = DjangoNoticeRepository(config=config, match_inbox=False)
        service = NoticeCrawlService(config=config, repository=repository)
        return service.crawl_recent(site.id, days=_SYNC_RECENT_DAYS, limit=_SYNC_FETCH_CAP)

    # generic: 모든 공지가 이 source 에 귀속되도록 source_override 로 리포지토리를 만든다.
    repository = DjangoNoticeRepository(
        config=config, match_inbox=False, source_override=source
    )
    service = NoticeCrawlService(config=config, repository=repository)
    return service.crawl_source(source, days=_SYNC_RECENT_DAYS, limit=_SYNC_FETCH_CAP)


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


def _notices_to_classify(source):
    """이 source 공지 중 가장 최근 10건(게시일 우선, 없으면 생성일)."""
    return list(
        Notice.objects.filter(source_id=source)
        .annotate(effective_at=Coalesce("published_at", "created_at"))
        .order_by("-effective_at", "-id")[:_SYNC_CLASSIFY_CAP]
    )


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


# ---------------------------------------------------------------------------
# 순차 작업 큐 + 단일 데몬 워커
# ---------------------------------------------------------------------------
_job_queue: "queue.Queue[tuple[int, int]]" = queue.Queue()
_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None


def enqueue(user, source) -> None:
    """(user, source) 동기화 작업을 큐에 넣고 워커가 돌고 있도록 보장한다.

    호출 즉시 상태를 'running' 으로 세워 폴링이 곧바로 진행 중임을 볼 수 있게 한다.
    이미 'running' 인 작업이 있으면 중복 등록하지 않는다 — 동기화 연타/재요청이 큐를
    부풀리거나 같은 작업을 반복 처리하지 않도록, 진행 중인 작업으로 붕괴시킨다.
    """
    try:
        existing = cache.get(_status_key(user.id, source.id))
    except Exception:  # noqa: BLE001 - 캐시 조회 실패 시엔 그냥 등록으로 진행
        existing = None
    if existing and existing.get("status") == "running":
        return

    _set_status(user.id, source.id, "running")
    _job_queue.put((user.id, source.id))
    _ensure_worker()


def _ensure_worker() -> None:
    """워커 데몬 스레드가 살아있지 않으면 시작한다(스레드-세이프, 최초 enqueue 시 지연 시작)."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop, name="sources-sync-worker", daemon=True
        )
        _worker_thread.start()


def _worker_loop() -> None:
    """큐에서 작업을 하나씩 꺼내 순차 처리한다. 한 작업의 실패가 워커를 죽이지 않는다."""
    while True:
        job = _job_queue.get()
        try:
            _process_job(job)
        finally:
            _job_queue.task_done()


def _process_job(job) -> None:
    """작업 하나를 처리한다: User/NoticeSource 를 새로 로드해 동기화하고 상태를 남긴다.

    예외가 나도 terminal 상태('failed')를 반드시 남기고, 스레드 로컬 DB 커넥션을
    작업 후 닫는다(스레드가 연 커넥션 누수 방지).
    """
    user_id, source_id = job
    from django.contrib.auth import get_user_model
    from django.db import connection

    from crawler.config_loader import load_config

    try:
        user = get_user_model().objects.get(id=user_id)
        source = NoticeSource.objects.get(id=source_id)
        result = run_sync_for_source(user, source, load_config())
        _set_status(
            user_id,
            source_id,
            "done",
            inbox_added=result.get("inbox_added", 0),
            message=result.get("message", ""),
        )
    except Exception:  # noqa: BLE001 - 워커 루프를 절대 죽이지 않는다
        log.exception("sync 작업 실패 (user=%s source=%s)", user_id, source_id)
        _set_status(user_id, source_id, "failed", message="동기화에 실패했어요.")
    finally:
        connection.close()


def _process_one(timeout=1) -> bool:
    """테스트 seam: 큐에서 작업 하나를 꺼내 (스레드 없이) 동기 처리한다.

    처리했으면 True, 타임아웃으로 처리할 작업이 없으면 False.
    """
    try:
        job = _job_queue.get(timeout=timeout)
    except queue.Empty:
        return False
    try:
        _process_job(job)
    finally:
        _job_queue.task_done()
    return True
