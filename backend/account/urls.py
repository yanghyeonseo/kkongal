from django.urls import path
from .views import SignUpView, SignInView, TokenRefreshView, LogoutView

app_name = 'account'
urlpatterns = [
    path("signup/", SignUpView.as_view()),
    path("signin/", SignInView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("logout/", LogoutView.as_view()),
]