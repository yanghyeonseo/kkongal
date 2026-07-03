from django.urls import path

from .views import (
    AiStatusView,
    InboxNoticeDetailView,
    InboxNoticeListView,
    InboxNoticeReadView,
    InboxNoticeSaveView,
)


app_name = "notices"

urlpatterns = [
    path("inbox/", InboxNoticeListView.as_view()),
    path("inbox/<int:inbox_notice_id>/", InboxNoticeDetailView.as_view()),
    path("inbox/<int:inbox_notice_id>/save/", InboxNoticeSaveView.as_view()),
    path("inbox/<int:inbox_notice_id>/read/", InboxNoticeReadView.as_view()),
]

# Mounted at /api/ai/ by kkongal/urls.py. Only the status banner endpoint remains;
# the pipeline itself runs through ai.service over the ORM, not HTTP.
ai_urlpatterns = [
    path("status/", AiStatusView.as_view()),
]
