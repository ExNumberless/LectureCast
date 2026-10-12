from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from courses.serializers import LectureSerializer

from .models import PipelineRun, SectionEdit, StageNode, StageRun
from .registry import STAGES


class PipelineRunRequestSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=tuple(STAGES))
    lecture_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)


class LectureReviewEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    number = serializers.IntegerField(min_value=1)
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    title = serializers.CharField(required=False, allow_blank=True, max_length=500)
    date = serializers.DateField(required=False, allow_null=True)


class CourseReviewRequestSerializer(serializers.Serializer):
    lectures = LectureReviewEntrySerializer(many=True, allow_empty=False)

    def validate_lectures(self, entries):
        ids = [entry["id"] for entry in entries]
        numbers = [entry["number"] for entry in entries]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each lecture may appear only once.")
        if len(numbers) != len(set(numbers)):
            raise serializers.ValidationError("Lecture numbers must be unique.")
        return entries


class StageDefinitionSerializer(serializers.Serializer):
    name = serializers.CharField()
    scope = serializers.ChoiceField(choices=("course", "lecture"))
    dependencies = serializers.ListField(child=serializers.CharField())
    capability = serializers.CharField()
    queue = serializers.CharField()
    is_gate = serializers.BooleanField()


class StagePreviewSerializer(serializers.Serializer):
    stage = serializers.CharField()
    lecture_id = serializers.IntegerField(allow_null=True)
    lecture_title = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    action = serializers.ChoiceField(choices=("reuse", "run"))


class CourseEstimateSerializer(serializers.Serializer):
    targets = serializers.DictField()
    nodes = StagePreviewSerializer(many=True)
    estimate = serializers.DictField()


class StageRunSerializer(serializers.ModelSerializer):
    stage = serializers.CharField(source="node.stage", read_only=True)
    lecture_id = serializers.IntegerField(source="node.lecture_id", allow_null=True, read_only=True)
    lecture_title = serializers.SerializerMethodField()

    class Meta:
        model = StageRun
        fields = ("id", "stage", "lecture_id", "lecture_title", "status", "progress", "log", "usage", "error")

    def get_lecture_title(self, obj) -> str | None:
        return obj.node.lecture.title if obj.node.lecture else None


class PipelineRunSerializer(serializers.ModelSerializer):
    stage_runs = StageRunSerializer(many=True, read_only=True)

    class Meta:
        model = PipelineRun
        fields = (
            "id",
            "course",
            "requested_by",
            "targets",
            "status",
            "estimate",
            "actual_usage",
            "error",
            "stage_runs",
            "created_at",
            "started_at",
            "finished_at",
        )
        read_only_fields = fields


class StageNodeSerializer(serializers.ModelSerializer):
    lecture_title = serializers.SerializerMethodField()
    run_by_email = serializers.EmailField(source="run_by.email", allow_null=True, read_only=True, default=None)
    latest_run = serializers.SerializerMethodField()

    class Meta:
        model = StageNode
        fields = (
            "id",
            "stage",
            "lecture",
            "lecture_title",
            "status",
            "settings_hash",
            "inputs_hash",
            "frozen",
            "error",
            "run_by_email",
            "latest_run",
            "updated_at",
        )
        read_only_fields = fields

    def get_lecture_title(self, obj) -> str | None:
        return obj.lecture.title if obj.lecture else None

    @extend_schema_field(StageRunSerializer(allow_null=True))
    def get_latest_run(self, obj):
        # Uses the prefetched runs when the view provides them (ordered by id).
        runs = list(obj.stage_runs.all())
        return StageRunSerializer(runs[-1]).data if runs else None


class CourseGraphSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    nodes = StageNodeSerializer(many=True)
    lectures = LectureSerializer(many=True)


class CourseReviewResponseSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    review = StageNodeSerializer()
    lectures = LectureSerializer(many=True)


class SectionEditSerializer(serializers.ModelSerializer):
    edited_by_email = serializers.EmailField(source="edited_by.email", allow_null=True, read_only=True, default=None)

    class Meta:
        model = SectionEdit
        fields = ("id", "n", "text", "edited_by_email", "edited_at")
        read_only_fields = fields


class NodeSectionSerializer(serializers.Serializer):
    n = serializers.IntegerField()
    title = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    original = serializers.CharField(allow_blank=True)
    edits = SectionEditSerializer(many=True)


class NodeSectionsSerializer(serializers.Serializer):
    node = StageNodeSerializer()
    editable = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    sections = NodeSectionSerializer(many=True)


class SectionUpdateRequestSerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=True, trim_whitespace=False, max_length=200_000)


class SectionUpdateResponseSerializer(serializers.Serializer):
    node = StageNodeSerializer()
    edit = SectionEditSerializer(allow_null=True)
    stale_nodes = StageNodeSerializer(many=True)
