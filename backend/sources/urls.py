from django.urls import path

from .views import SourceSubscriptionDetailView, SourceSubscriptionListView


app_name = "sources"

urlpatterns = [
    path("", SourceSubscriptionListView.as_view()),
    path("<int:subscription_id>/", SourceSubscriptionDetailView.as_view()),
]
