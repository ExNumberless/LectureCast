from django.urls import path

from .views import (
    CourseEstimateView,
    CoursePipelineView,
    CourseReviewView,
    CourseRunView,
    PipelineRegistryView,
    RunDetailView,
)

urlpatterns = [
    path("pipeline", PipelineRegistryView.as_view(), name="pipeline-registry"),
    path("courses/<int:course_id>/graph", CoursePipelineView.as_view(), name="course-pipeline-graph"),
    path("courses/<int:course_id>/estimate", CourseEstimateView.as_view(), name="course-pipeline-estimate"),
    path("courses/<int:course_id>/runs", CourseRunView.as_view(), name="course-pipeline-runs"),
    path("courses/<int:course_id>/review", CourseReviewView.as_view(), name="course-review"),
    path("runs/<int:run_id>", RunDetailView.as_view(), name="pipeline-run-detail"),
]
