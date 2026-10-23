from urllib.parse import urlsplit

from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import serializers

from .models import Course, Lecture, Slide
from .providers import get_provider, validate_provider_settings


class ProviderSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    source_kind = serializers.ChoiceField(choices=["url", "upload"])
    settings_schema = serializers.JSONField()


class CourseSerializer(serializers.ModelSerializer):
    source_url = serializers.URLField(required=False, allow_blank=True)
    source_file = serializers.CharField(source="source_file.name", read_only=True)
    source_upload = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Course
        fields = (
            "id",
            "owner",
            "title",
            "source_url",
            "source_file",
            "source_upload",
            "provider",
            "plugin",
            "settings",
            "license",
            "visibility",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "visibility", "created_at", "updated_at")

    def validate(self, attrs):
        provider_id = attrs.get("provider", getattr(self.instance, "provider", None))
        provider = get_provider(provider_id) if provider_id else None
        if provider is None:
            raise serializers.ValidationError({"provider": "This provider is not enabled."})

        source_url = attrs.get("source_url", getattr(self.instance, "source_url", ""))
        source_upload = attrs.get("source_upload", "")
        source_file = getattr(self.instance, "source_file", None)
        if provider.source_kind == "url":
            if not source_url:
                raise serializers.ValidationError({"source_url": "This field is required for this provider."})
            if urlsplit(source_url).scheme not in {"http", "https"}:
                raise serializers.ValidationError({"source_url": "Only HTTP and HTTPS course URLs are allowed."})
            if source_upload or source_file:
                raise serializers.ValidationError({"source_file": "This provider accepts a URL, not an upload."})
        else:
            if not source_upload and not source_file:
                raise serializers.ValidationError({"source_upload": "Upload a ZIP archive for this provider."})
            if source_upload:
                expected_prefix = f"course-sources/{self.context['request'].user.pk}/"
                if not source_upload.startswith(expected_prefix) or not source_upload.lower().endswith(".zip"):
                    raise serializers.ValidationError({"source_upload": "Choose a valid ZIP upload."})
                if not default_storage.exists(source_upload):
                    raise serializers.ValidationError({"source_upload": "The ZIP upload could not be found."})
            if source_url:
                raise serializers.ValidationError({"source_url": "This provider accepts an upload, not a URL."})

        settings_value = attrs.get("settings", getattr(self.instance, "settings", {}))
        try:
            validate_provider_settings(provider, settings_value)
        except ValueError as error:
            raise serializers.ValidationError({"settings": str(error)}) from error

        plugin = attrs.get("plugin", getattr(self.instance, "plugin", ""))
        allowed_plugins = getattr(settings, "COURSE_PLUGIN_ALLOWLIST", [])
        if plugin and plugin not in allowed_plugins:
            raise serializers.ValidationError({"plugin": "This plugin is not enabled."})
        return attrs

    def create(self, validated_data):
        source_upload = validated_data.pop("source_upload", None)
        course = Course(**validated_data)
        if source_upload:
            course.source_file.name = source_upload
        course.save()
        return course

    def update(self, instance, validated_data):
        source_upload = validated_data.pop("source_upload", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if source_upload:
            instance.source_file.name = source_upload
        instance.save()
        return instance


class LectureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lecture
        fields = ("id", "number", "name", "title", "date", "included", "audio", "duration_ms")
        read_only_fields = fields


class SlideSerializer(serializers.ModelSerializer):
    image = serializers.CharField(source="image.name", read_only=True)

    class Meta:
        model = Slide
        fields = (
            "id",
            "n",
            "kind",
            "title",
            "image",
            "markdown",
            "code",
            "language",
            "width",
            "height",
            "narration",
            "start_ms",
            "end_ms",
            "source",
            "locator",
        )
        read_only_fields = fields
