from rest_framework import serializers

from courses.models import Course

from .models import OPEN_LICENSES, ContentReport, Publication, TakedownRequest


class LicenseSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class PublicationRequestSerializer(serializers.Serializer):
    license = serializers.ChoiceField(
        choices=sorted(OPEN_LICENSES.items()),
        error_messages={"invalid_choice": "The catalog only accepts open licenses (CC BY, CC BY-SA or CC0)."},
    )
    attribution = serializers.CharField(max_length=2000)


class PublicationSerializer(serializers.ModelSerializer):
    license_name = serializers.SerializerMethodField()

    class Meta:
        model = Publication
        fields = (
            "id",
            "course",
            "status",
            "license",
            "license_name",
            "attribution",
            "requested_at",
            "reviewed_at",
            "review_note",
        )
        read_only_fields = fields

    def get_license_name(self, obj) -> str:
        return OPEN_LICENSES.get(obj.license, obj.license)


class CoverageLectureSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    title = serializers.CharField()
    stages = serializers.ListField(child=serializers.CharField(), help_text="Lecture stages this lecture has reached.")


class ContributorSerializer(serializers.Serializer):
    stage = serializers.CharField()
    names = serializers.ListField(child=serializers.CharField())


class CatalogCourseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    provider = serializers.CharField()
    source_url = serializers.CharField(allow_blank=True)
    license = serializers.CharField()
    license_name = serializers.CharField()
    attribution = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    playable_lectures = serializers.IntegerField()
    totals = serializers.DictField(child=serializers.IntegerField())
    lectures = CoverageLectureSerializer(many=True)
    contributors = ContributorSerializer(many=True)


class ContentReportRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=5000)
    node = serializers.IntegerField(required=False, allow_null=True)


class ContentReportSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)

    class Meta:
        model = ContentReport
        fields = ("id", "course", "course_title", "node", "reason", "status", "created_at", "resolution")
        read_only_fields = fields


class TakedownRequestSerializer(serializers.ModelSerializer):
    # Only courses in the catalog can be named.
    course = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.filter(publication__status=Publication.Status.APPROVED)
    )

    class Meta:
        model = TakedownRequest
        fields = ("id", "course", "name", "email", "details", "status", "created_at", "note")
        read_only_fields = ("id", "status", "created_at", "note")


class ModerationQueueSerializer(serializers.Serializer):
    publications = PublicationSerializer(many=True)
    reports = ContentReportSerializer(many=True)
    takedowns = TakedownRequestSerializer(many=True)


class ModerationActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("approve", "reject", "unpublish", "resolve", "take_down", "dismiss"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
