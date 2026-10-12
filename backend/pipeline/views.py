from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_202_ACCEPTED

from courses.models import Course
from courses.serializers import LectureSerializer

from .models import PipelineRun, StageNode
from .registry import public_stage_registry, source_stage
from .scheduler import create_run, node_inputs_hash, node_settings_hash, preview_run, sync_course_staleness
from .sections import EDITABLE_STAGES, edit_block_reason, node_sections, save_section
from .serializers import (
    CourseEstimateSerializer,
    CourseGraphSerializer,
    CourseReviewRequestSerializer,
    CourseReviewResponseSerializer,
    NodeSectionsSerializer,
    PipelineRunRequestSerializer,
    PipelineRunSerializer,
    SectionUpdateRequestSerializer,
    SectionUpdateResponseSerializer,
    StageDefinitionSerializer,
    StageNodeSerializer,
)


class PipelineRegistryView(GenericAPIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses=StageDefinitionSerializer(many=True), tags=["pipeline"])
    def get(self, request):
        return Response(public_stage_registry())


class CourseBaseView(GenericAPIView):
    permission_classes = (IsAuthenticated,)

    def get_course(self):
        if getattr(self, "swagger_fake_view", False):
            return None
        return get_object_or_404(Course, pk=self.kwargs["course_id"], owner=self.request.user)


class CoursePipelineView(CourseBaseView):
    serializer_class = PipelineRunRequestSerializer

    @extend_schema(responses=CourseGraphSerializer, tags=["pipeline"])
    def get(self, request, course_id):
        course = self.get_course()
        sync_course_staleness(course)
        nodes = course.stage_nodes.select_related("lecture", "run_by").prefetch_related("stage_runs__node__lecture")
        lectures = course.lectures.order_by("number", "id")
        return Response(
            {
                "course_id": course.pk,
                "nodes": StageNodeSerializer(nodes, many=True).data,
                "lectures": LectureSerializer(lectures, many=True).data,
            }
        )


class CourseEstimateView(CourseBaseView):
    serializer_class = PipelineRunRequestSerializer

    @extend_schema(request=PipelineRunRequestSerializer, responses=CourseEstimateSerializer, tags=["pipeline"])
    def post(self, request, course_id):
        course = self.get_course()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sync_course_staleness(course)
        return Response(preview_run(course, **serializer.validated_data))


class CourseRunView(CourseBaseView):
    serializer_class = PipelineRunRequestSerializer

    @extend_schema(request=PipelineRunRequestSerializer, responses=PipelineRunSerializer, tags=["pipeline"])
    def post(self, request, course_id):
        course = self.get_course()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = create_run(course, request.user, **serializer.validated_data)
        return Response(PipelineRunSerializer(run).data, status=HTTP_202_ACCEPTED)


class CourseReviewView(CourseBaseView):
    serializer_class = CourseReviewRequestSerializer

    @extend_schema(
        request=CourseReviewRequestSerializer,
        responses=CourseReviewResponseSerializer,
        tags=["pipeline"],
    )
    def post(self, request, course_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = serializer.validated_data["lectures"]
        with transaction.atomic():
            course = Course.objects.select_for_update().get(pk=self.kwargs["course_id"], owner=request.user)
            sync_course_staleness(course)
            source = course.stage_nodes.filter(stage=source_stage(course), lecture__isnull=True).first()
            if source is None or source.status != StageNode.Status.SUCCEEDED:
                raise serializers.ValidationError(
                    {"lectures": "Fetch or upload course materials before reviewing lectures."}
                )

            lectures = list(course.lectures.all())
            by_id = {lecture.id: lecture for lecture in lectures}
            entry_ids = {entry["id"] for entry in entries}
            if not entry_ids.issubset(by_id):
                raise serializers.ValidationError({"lectures": "One or more lecture IDs do not belong to this course."})

            course.lectures.update(included=False)
            for entry in entries:
                lecture = by_id[entry["id"]]
                lecture.number = entry["number"]
                lecture.name = entry.get("name", lecture.name)
                lecture.title = entry.get("title", lecture.title)
                lecture.date = entry.get("date", lecture.date)
                lecture.included = True
                lecture.save(update_fields=["number", "name", "title", "date", "included"])

            review, _ = StageNode.objects.get_or_create(
                course=course, stage="review", lecture=None, defaults={"status": StageNode.Status.PENDING}
            )
            if review.frozen:
                raise serializers.ValidationError({"lectures": "This lecture list is frozen and cannot be changed."})
            review.status = StageNode.Status.SUCCEEDED
            review.error = ""
            review.run_by = request.user
            review.settings_hash = node_settings_hash(course, "review")
            review.inputs_hash = node_inputs_hash(course, "review", None)
            review.save()
            sync_course_staleness(course)

        return Response(
            {
                "course_id": course.pk,
                "review": StageNodeSerializer(review).data,
                "lectures": LectureSerializer(course.lectures.order_by("number", "id"), many=True).data,
            }
        )


class RunDetailView(GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PipelineRunSerializer

    def get(self, request, run_id):
        run = get_object_or_404(
            PipelineRun.objects.filter(course__owner=request.user).prefetch_related("stage_runs__node__lecture"),
            pk=run_id,
        )
        return Response(self.get_serializer(run).data)


class NodeBaseView(GenericAPIView):
    permission_classes = (IsAuthenticated,)

    def get_node(self):
        return get_object_or_404(
            StageNode.objects.select_related("course", "lecture", "run_by"),
            pk=self.kwargs["node_id"],
            course__owner=self.request.user,
        )


class NodeSectionsView(NodeBaseView):
    serializer_class = NodeSectionsSerializer

    @extend_schema(responses=NodeSectionsSerializer, tags=["pipeline"])
    def get(self, request, node_id):
        node = self.get_node()
        if node.stage not in EDITABLE_STAGES or not node.output_prefix:
            raise NotFound("This stage has no editable output.")
        reason = edit_block_reason(node)
        return Response(
            NodeSectionsSerializer(
                {"node": node, "editable": reason is None, "reason": reason, "sections": node_sections(node)}
            ).data
        )


class NodeSectionView(NodeBaseView):
    serializer_class = SectionUpdateRequestSerializer

    @extend_schema(request=SectionUpdateRequestSerializer, responses=SectionUpdateResponseSerializer, tags=["pipeline"])
    def put(self, request, node_id, n):
        self.get_node()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node, edit, stale = save_section(node_id, n, serializer.validated_data["text"], request.user)
        return Response(SectionUpdateResponseSerializer({"node": node, "edit": edit, "stale_nodes": stale}).data)
