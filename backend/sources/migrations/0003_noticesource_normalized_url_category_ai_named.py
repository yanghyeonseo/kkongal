"""normalized_url(dedup 키) + category + ai_named 추가.

normalized_url 은 unique 라, 기존 여러 행에 빈 값을 한꺼번에 넣으면 제약에 걸린다.
그래서 3단계로 진행한다: (1) unique 없이 컬럼 추가 → (2) 값 backfill 및 같은 게시판으로
정규화되는 중복 소스 병합 → (3) unique 제약 부여.
"""
from __future__ import annotations

from django.db import migrations, models


def backfill_and_merge(apps, schema_editor):
    # 병합 로직은 sources.dedup 에 두고 마이그레이션·테스트가 공유한다(단일 진실원본).
    from sources.dedup import backfill_normalized_urls

    backfill_normalized_urls(
        apps.get_model("sources", "NoticeSource"),
        apps.get_model("sources", "SourceSubscription"),
        apps.get_model("notices", "Notice"),
    )


def noop_reverse(apps, schema_editor):
    # 병합은 되돌릴 수 없다(정보 손실). 컬럼 제거만 역방향에서 처리된다.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sources", "0002_noticesource_extraction_profile_and_more"),
        ("notices", "0002_inboxnotice_classified_by_llm_notice_enriched_by_llm"),
    ]

    operations = [
        migrations.AddField(
            model_name="noticesource",
            name="category",
            field=models.CharField(blank=True, default="etc", max_length=32),
        ),
        migrations.AddField(
            model_name="noticesource",
            name="ai_named",
            field=models.BooleanField(default=False),
        ),
        # 1) unique 없이 추가
        migrations.AddField(
            model_name="noticesource",
            name="normalized_url",
            field=models.URLField(blank=True, default="", max_length=1024),
        ),
        # 2) 값 채우기 + 중복 병합
        migrations.RunPython(backfill_and_merge, noop_reverse),
        # 3) unique 제약 부여
        migrations.AlterField(
            model_name="noticesource",
            name="normalized_url",
            field=models.URLField(blank=True, max_length=1024, unique=True),
        ),
    ]
