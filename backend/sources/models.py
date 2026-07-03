from django.db import models
from django.conf import settings
from django.utils import timezone


class NoticeSource(models.Model):
    # 자동 수집 전략(어떤 추출기가 이 사이트를 담당하는지). generic 파이프라인이 크롤에
    # 성공하면 실제로 통한 전략을 여기에 기록해 다음 크롤부터 재사용한다.
    #   builtin      : crawler/scrapers/REGISTRY 의 손파서(sites.json 카탈로그 사이트)
    #   rss          : RSS/Atom 피드
    #   json_api     : 사이트 내부 JSON API
    #   heuristic    : 반복블록 HTML 휴리스틱
    #   llm_profile  : LLM 이 학습한 셀렉터 레시피
    #   ""           : 아직 미결정(첫 크롤에서 계단식으로 탐색)
    SCRAPER_KINDS = (
        ("", "미결정"),
        ("builtin", "builtin"),
        ("rss", "rss"),
        ("json_api", "json_api"),
        ("heuristic", "heuristic"),
        ("llm_profile", "llm_profile"),
    )

    # 사람이 읽는 표시명(사용자 편집 가능). 등록 시 카탈로그 이름이나 도메인에서 채운다.
    name = models.CharField(max_length=128, blank=True)
    # 사용자가 처음 등록한 원본 URL(실제 fetch 대상). 표기 차이를 흡수하려면 normalized_url 을 쓴다.
    url = models.URLField(max_length=1024, unique=True)
    # 정규화 URL — 같은 게시판을 하나로 모으는 dedup 키(unique). 등록 시 url 에서 계산한다.
    # 이 키로 NoticeSource 를 get_or_create 하므로, 표기만 다른 같은 사이트는 하나로 합쳐지고
    # 먼저 학습된 크롤 레시피(extraction_profile)를 다음 구독자가 그대로 재사용한다.
    normalized_url = models.URLField(max_length=1024, unique=True, blank=True)
    # 카테고리(도메인). 카탈로그 필터에 쓴다. 첫 크롤 확정 시 AI 가 채우며, 미분류는 "etc".
    category = models.CharField(max_length=32, blank=True, default="etc")
    # AI 로 name/category 를 이미 채웠는지. True 면 매 동기화마다 다시 LLM 을 부르지 않는다.
    ai_named = models.BooleanField(default=False)
    # 사이트 파비콘 URL. 등록 시 Google s2 서비스로 계산해 저장한다(사이트를 직접 받지 않음).
    favicon_url = models.URLField(max_length=1024, blank=True)
    crawl_interval_minutes = models.IntegerField(default=60)
    crawled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    # --- generic 자동 수집(임의 사이트) 관련 ---
    scraper_kind = models.CharField(
        max_length=16, choices=SCRAPER_KINDS, blank=True, default=""
    )
    # 학습된 추출 레시피. 전략마다 형태가 다르다:
    #   rss        -> {"feed": "<피드 url>"}
    #   json_api   -> {"endpoint": "...", "list_path": "...", "fields": {...}}
    #   heuristic  -> {"row": "<셀렉터>", "title": "...", "link": "...", "date": "..."}
    #   llm_profile-> {"row": "...", "title": "...", "link": "...", "date": "..."}
    extraction_profile = models.JSONField(null=True, blank=True)
    # fetch 백엔드: http(httpx) | impersonate(curl_cffi TLS 위장) | browser(playwright).
    # generic 파이프라인이 필요 시 자동 승격하며, 성공한 값을 저장해 다음부터 바로 쓴다.
    render = models.CharField(max_length=16, blank=True, default="http")
    # 마지막으로 1건 이상 추출에 성공한 시각. 프로파일이 stale(0건 반복)해지면 재학습 판단에 쓴다.
    last_extract_ok_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # 어떤 생성 경로(직접 create 포함)든 normalized_url 이 비지 않도록 보장한다.
        # unique 제약이 걸린 컬럼이라 "" 가 여러 개면 충돌하기 때문.
        if not self.normalized_url and self.url:
            from .url_normalize import normalize_url

            self.normalized_url = normalize_url(self.url) or self.url
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def is_recipe_confirmed(self) -> bool:
        """크롤 레시피가 확정(첫 성공 크롤로 학습)됐는지. 카탈로그 공유 기준."""
        return bool(self.scraper_kind)

    @classmethod
    def resolve(cls, url: str, *, defaults: dict | None = None):
        """정규화 URL 을 키로 NoticeSource 를 가져오거나 만든다(같은 게시판 = 하나의 소스).

        표기만 다른 같은 사이트가 하나로 합쳐지므로, 먼저 학습된 크롤 레시피를 다음
        구독자가 그대로 재사용한다(사용자 증가 = 자연 스케일링). (source, created) 반환.
        """
        from .url_normalize import normalize_url

        key = normalize_url(url) or url
        create_defaults = dict(defaults or {})
        create_defaults["url"] = create_defaults.get("url", url)
        create_defaults["normalized_url"] = key
        return cls.objects.get_or_create(normalized_url=key, defaults=create_defaults)


class SourceSubscription(models.Model):
    user_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="source_subscriptions",
    )
    source_id = models.ForeignKey(
        NoticeSource,
        on_delete=models.CASCADE,
        db_column="source_id",
        related_name="subscriptions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "source_id"],
                name="unique_user_source_subscription",
            )
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.source_id}"
