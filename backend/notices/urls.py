from django.urls import path

from .views import InboxNoticeDetailView, InboxNoticeListView


app_name = "notices"

urlpatterns = [
    path("inbox/", InboxNoticeListView.as_view()),
    path("inbox/<int:inbox_notice_id>/", InboxNoticeDetailView.as_view()),
]
