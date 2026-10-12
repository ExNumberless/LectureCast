from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CourseViewSet, LectureSlidesView, ProviderListView, UploadUrlView

router = DefaultRouter()
router.register("courses", CourseViewSet, basename="course")

urlpatterns = [
    path("providers", ProviderListView.as_view(), name="provider-list"),
    path("courses/upload-url", UploadUrlView.as_view(), name="course-upload-url"),
    path("lectures/<int:lecture_id>/slides", LectureSlidesView.as_view(), name="lecture-slides"),
    path("", include(router.urls)),
]
