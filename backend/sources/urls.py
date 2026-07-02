from django.urls import path

from .views import (
    SourceCatalogView,
    SourceSubscriptionDetailView,
    SourceSubscriptionListView,
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
    path("<int:source_id>/sync/", SourceSyncView.as_view(), name="sync"),
]
