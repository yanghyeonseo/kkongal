"""정규화 URL backfill + 중복 소스 병합.

마이그레이션(historical 모델)과 테스트(실 모델)가 공유하도록 모델 클래스를 인자로 받는다.
같은 게시판으로 정규화되는 여러 NoticeSource 를 하나(survivor)로 합치고, 구독/공지를
survivor 로 이관한다. 유니크 제약(user×source, source×url)에 걸리는 항목은 중복이므로 삭제한다.

주의: FK 필드명이 ``source_id`` 라 원시 pk 애트리뷰트는 ``source_id_id`` 다.
객체가 아닌 pk 를 대입하려면 ``obj.source_id_id = pk`` 를 써야 한다(객체 대입은 ValueError).
"""
from __future__ import annotations

from .url_normalize import normalize_url


def backfill_normalized_urls(NoticeSource, SourceSubscription, Notice) -> None:
    """모든 NoticeSource 에 normalized_url 을 채우고, 같은 키로 겹치는 행을 병합한다."""
    seen: dict[str, int] = {}
    for src in NoticeSource.objects.all().order_by("id"):
        key = normalize_url(src.url) or src.url
        survivor_id = seen.get(key)
        if survivor_id is None:
            src.normalized_url = key
            src.save(update_fields=["normalized_url"])
            seen[key] = src.id
            continue

        # 중복 → survivor 로 구독/공지를 이관하고 이 행을 삭제.
        for sub in SourceSubscription.objects.filter(source_id=src.id):
            already = SourceSubscription.objects.filter(
                user_id=sub.user_id_id, source_id=survivor_id
            ).exists()
            if already:
                sub.delete()
            else:
                sub.source_id_id = survivor_id
                sub.save(update_fields=["source_id"])

        for notice in Notice.objects.filter(source_id=src.id):
            already = Notice.objects.filter(
                source_id=survivor_id, url=notice.url
            ).exists()
            if already:
                notice.delete()
            else:
                notice.source_id_id = survivor_id
                notice.save(update_fields=["source_id"])

        src.delete()
