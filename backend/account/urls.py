from django.urls import path
from .views import (
    InterestDetailView,
    InterestListView,
    LogoutView,
    MeView,
    OnboardingCompleteView,
    ProfileAttributeDetailView,
    ProfileAttributeListView,
    ProfileView,
    SignInView,
    SignUpView,
    TokenRefreshView,
)

app_name = 'account'
urlpatterns = [
    path("signup/", SignUpView.as_view()),
    path("signin/", SignInView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("me/", MeView.as_view()),
    path("onboarding/complete/", OnboardingCompleteView.as_view()),
    path("profile/", ProfileView.as_view()),
    path("profile/attributes/", ProfileAttributeListView.as_view()),
    path("profile/attributes/<int:attribute_id>/", ProfileAttributeDetailView.as_view()),
]

interest_urlpatterns = [
    path("", InterestListView.as_view()),
    path("<int:interest_id>/", InterestDetailView.as_view()),
]
