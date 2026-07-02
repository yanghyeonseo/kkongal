from django.urls import path

from .views import AlertChannelDetailView, AlertChannelListView, AlertLogListView


app_name = "alert"

urlpatterns = [
    path("alert-channels/", AlertChannelListView.as_view()),
    path("alert-channels/<int:channel_id>/", AlertChannelDetailView.as_view()),
    path("alert-logs/", AlertLogListView.as_view()),
]
