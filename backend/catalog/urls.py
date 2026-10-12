from django.urls import path

from .views import (
    CatalogCourseView,
    CatalogView,
    ContentReportView,
    CoursePublicationView,
    LicenseListView,
    ModeratePublicationView,
    ModerateReportView,
    ModerateTakedownView,
    ModerationQueueView,
    TakedownRequestView,
)

urlpatterns = [
    path("catalog", CatalogView.as_view(), name="catalog"),
    path("catalog/licenses", LicenseListView.as_view(), name="catalog-licenses"),
    path("catalog/takedowns", TakedownRequestView.as_view(), name="catalog-takedowns"),
    path("catalog/<int:course_id>", CatalogCourseView.as_view(), name="catalog-course"),
    path("catalog/<int:course_id>/reports", ContentReportView.as_view(), name="catalog-reports"),
    path("courses/<int:course_id>/publication", CoursePublicationView.as_view(), name="course-publication"),
    path("moderation", ModerationQueueView.as_view(), name="moderation-queue"),
    path(
        "moderation/publications/<int:publication_id>", ModeratePublicationView.as_view(), name="moderate-publication"
    ),
    path("moderation/reports/<int:report_id>", ModerateReportView.as_view(), name="moderate-report"),
    path("moderation/takedowns/<int:takedown_id>", ModerateTakedownView.as_view(), name="moderate-takedown"),
]
