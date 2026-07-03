"""
URL configuration for kkongal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from account.urls import interest_urlpatterns
from notices.urls import ai_urlpatterns
from sources.urls import sources_urlpatterns


def healthz(_request):
    """로드밸런서(ALB) 헬스체크용 경량 엔드포인트. 인증·DB 접근 없이 200 을 반환한다."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/healthz/', healthz, name='healthz'),
    path('api/account/', include('account.urls')),
    path('api/interests/', include((interest_urlpatterns, 'interests'))),
    path('api/subscriptions/', include('sources.urls')),
    path('api/sources/', include(sources_urlpatterns)),
    path('api/notices/', include('notices.urls')),
    path('api/ai/', include((ai_urlpatterns, 'ai'))),
    path('api/', include('alert.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

]
