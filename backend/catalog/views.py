from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED
from rest_framework.throttling import ScopedRateThrottle

from courses.models import Course, Lecture
from pipeline.models import StageNode

from .models import OPEN_LICENSES, ContentReport, Publication, TakedownRequest
from .serializers import (
    CatalogCourseSerializer,
    ContentReportRequestSerializer,
    ContentReportSerializer,
    LicenseSerializer,
    ModerationActionSerializer,
    ModerationQueueSerializer,
    PublicationRequestSerializer,
    PublicationSerializer,
    TakedownRequestSerializer,
)
from .services import (
    catalog_entry,
    handle_takedown,
    moderate_publication,
    request_publication,
    resolve_report,
)


class LicenseListView(GenericAPIView):
    permission_classes = (AllowAny,)

    @extend_schema(responses=LicenseSerializer(many=True), tags=["catalog"])
    def get(self, request):
        return Response([{"id": key, "name": name} for key, name in sorted(OPEN_LICENSES.items())])


class CoursePublicationView(GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PublicationRequestSerializer

    def get_course(self):
        return get_object_or_404(Course, pk=self.kwargs["course_id"], owner=self.request.user)

    @extend_schema(responses=PublicationSerializer, tags=["catalog"])
    def get(self, request, course_id):
        publication = get_object_or_404(Publication, course=self.get_course())
        return Response(PublicationSerializer(publication).data)

    @extend_schema(request=PublicationRequestSerializer, responses={201: PublicationSerializer}, tags=["catalog"])
    def post(self, request, course_id):
        course = self.get_course()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publication = request_publication(course, request.user, **serializer.validated_data)
        return Response(PublicationSerializer(publication).data, status=HTTP_201_CREATED)


def _published():
    return (
        Publication.objects.filter(status=Publication.Status.APPROVED)
        .select_related("course")
        .prefetch_related(
            Prefetch("course__lectures", queryset=Lecture.objects.order_by("number", "id")),
            Prefetch("course__stage_nodes", queryset=StageNode.objects.select_related("run_by")),
        )
    )


class CatalogView(GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = CatalogCourseSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("include_unplayable", bool, description="Also list courses with no playable lecture yet.")
        ],
        responses=CatalogCourseSerializer(many=True),
        tags=["catalog"],
    )
    def get(self, request):
        entries = [catalog_entry(publication) for publication in _published()]
        if request.query_params.get("include_unplayable") not in {"1", "true"}:
            entries = [entry for entry in entries if entry["playable_lectures"] > 0]
        entries.sort(key=lambda entry: entry["title"].lower())
        return Response(CatalogCourseSerializer(entries, many=True).data)


class CatalogCourseView(GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = CatalogCourseSerializer

    @extend_schema(responses=CatalogCourseSerializer, tags=["catalog"])
    def get(self, request, course_id):
        publication = get_object_or_404(_published(), course_id=course_id)
        return Response(CatalogCourseSerializer(catalog_entry(publication)).data)


class ContentReportView(GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ContentReportRequestSerializer

    @extend_schema(request=ContentReportRequestSerializer, responses={201: ContentReportSerializer}, tags=["catalog"])
    def post(self, request, course_id):
        publication = get_object_or_404(_published(), course_id=course_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_id = serializer.validated_data.get("node")
        node = get_object_or_404(StageNode, pk=node_id, course=publication.course) if node_id else None
        report = ContentReport.objects.create(
            course=publication.course, node=node, reporter=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(ContentReportSerializer(report).data, status=HTTP_201_CREATED)


class TakedownRequestView(GenericAPIView):
    """Rights holders may not have accounts, so this is open to anyone and rate limited."""

    permission_classes = (AllowAny,)
    serializer_class = TakedownRequestSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "takedown"

    @extend_schema(request=TakedownRequestSerializer, responses={201: TakedownRequestSerializer}, tags=["catalog"])
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        takedown = serializer.save()
        return Response(TakedownRequestSerializer(takedown).data, status=HTTP_201_CREATED)


class ModerationQueueView(GenericAPIView):
    permission_classes = (IsAdminUser,)
    serializer_class = ModerationQueueSerializer

    @extend_schema(responses=ModerationQueueSerializer, tags=["moderation"])
    def get(self, request):
        return Response(
            ModerationQueueSerializer(
                {
                    "publications": Publication.objects.filter(status=Publication.Status.PENDING),
                    "reports": ContentReport.objects.filter(status=ContentReport.Status.OPEN).select_related("course"),
                    "takedowns": TakedownRequest.objects.filter(status=TakedownRequest.Status.OPEN),
                }
            ).data
        )


class ModeratePublicationView(GenericAPIView):
    permission_classes = (IsAdminUser,)
    serializer_class = ModerationActionSerializer

    @extend_schema(request=ModerationActionSerializer, responses=PublicationSerializer, tags=["moderation"])
    def post(self, request, publication_id):
        publication = get_object_or_404(Publication, pk=publication_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publication = moderate_publication(publication, request.user, **serializer.validated_data)
        return Response(PublicationSerializer(publication).data)


class ModerateReportView(GenericAPIView):
    permission_classes = (IsAdminUser,)
    serializer_class = ModerationActionSerializer

    @extend_schema(request=ModerationActionSerializer, responses=ContentReportSerializer, tags=["moderation"])
    def post(self, request, report_id):
        report = get_object_or_404(ContentReport, pk=report_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["action"] == "unpublish":
            publication = get_object_or_404(Publication, course=report.course)
            moderate_publication(publication, request.user, "unpublish", serializer.validated_data["note"])
        report = resolve_report(report, request.user, serializer.validated_data["note"])
        return Response(ContentReportSerializer(report).data)


class ModerateTakedownView(GenericAPIView):
    permission_classes = (IsAdminUser,)
    serializer_class = ModerationActionSerializer

    @extend_schema(request=ModerationActionSerializer, responses=TakedownRequestSerializer, tags=["moderation"])
    def post(self, request, takedown_id):
        takedown = get_object_or_404(TakedownRequest, pk=takedown_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        takedown = handle_takedown(takedown, request.user, **serializer.validated_data)
        return Response(TakedownRequestSerializer(takedown).data)
