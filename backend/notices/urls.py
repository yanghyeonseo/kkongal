from django.urls import path

from .views import (
    AiInboxNoticeCreateView,
    AiNoticeCandidateListView,
    AiNoticeListView,
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

ai_urlpatterns = [
    path("status/", AiStatusView.as_view()),
    path("notices/", AiNoticeListView.as_view()),
    path("notices/<int:notice_id>/candidates/", AiNoticeCandidateListView.as_view()),
    path("inbox-notices/", AiInboxNoticeCreateView.as_view()),
]
