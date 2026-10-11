from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from . import views


@require_GET
@ensure_csrf_cookie
def csrf_cookie(request):
    return JsonResponse({"csrf_cookie_name": settings.CSRF_COOKIE_NAME})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/csrf/", csrf_cookie),
    # Headless mode keeps the OAuth redirect and callback views available here.
    path("api/auth/", include("allauth.urls")),
    path("api/auth/", include("allauth.headless.urls")),
    path("api/health", views.health),
]
