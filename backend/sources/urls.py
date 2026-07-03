from django.urls import path

from .views import (
    SourceCatalogView,
    SourceDetailView,
    SourceSubscriptionDetailView,
    SourceSubscriptionListView,
    SourceSyncStatusView,
    SourceSyncView,
)


app_name = "sources"

# 프로젝트 urlconf 에서 /api/subscriptions/ 로 마운트된다(구독 CRUD).
urlpatterns = [
    path("", SourceSubscriptionListView.as_view()),
    path("<int:subscription_id>/", SourceSubscriptionDetailView.as_view()),
]

# 프로젝트 urlconf 에서 /api/sources/ 로 마운트할 카탈로그 + 온디맨드 동기화 라우트.
# (notices.urls 의 ai_urlpatterns 처럼 리드가 kkongal/urls.py 에서 include 한다.)
sources_urlpatterns = [
    path("catalog/", SourceCatalogView.as_view(), name="catalog"),
    # 정적 경로는 <int:source_id> 라우트보다 먼저 둔다.
    path("sync/status/", SourceSyncStatusView.as_view(), name="sync-status"),
    path("<int:source_id>/sync/", SourceSyncView.as_view(), name="sync"),
    path("<int:source_id>/", SourceDetailView.as_view(), name="detail"),
]
