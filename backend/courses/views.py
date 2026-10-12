from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Course, Lecture, Slide
from .providers import enabled_providers
from .serializers import CourseSerializer, ProviderSerializer, SlideSerializer


class ProviderListView(GenericAPIView):
    serializer_class = ProviderSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses=ProviderSerializer(many=True), tags=["providers"])
    def get(self, request):
        providers = [
            {
                "id": provider.id,
                "name": provider.name,
                "description": provider.description,
                "source_kind": provider.source_kind,
                "settings_schema": provider.settings_schema,
            }
            for provider in enabled_providers()
        ]
        return Response(self.get_serializer(providers, many=True).data)


class UploadUrlSerializer(serializers.Serializer):
    provider = serializers.CharField()
    filename = serializers.CharField(max_length=255)

    def validate(self, attrs):
        provider = next((item for item in enabled_providers() if item.id == attrs["provider"]), None)
        if provider is None or provider.source_kind != "upload":
            raise serializers.ValidationError({"provider": "This provider does not accept uploads."})
        if not attrs["filename"].lower().endswith(".zip"):
            raise serializers.ValidationError({"filename": "Choose a ZIP archive."})
        return attrs


class UploadUrlResponseSerializer(serializers.Serializer):
    url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())
    key = serializers.CharField()


class UploadUrlView(GenericAPIView):
    serializer_class = UploadUrlSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses=UploadUrlResponseSerializer, tags=["courses"])
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = f"course-sources/{request.user.pk}/{uuid4()}.zip"
        client = default_storage.bucket.meta.client
        signed = client.generate_presigned_post(
            settings.AWS_STORAGE_BUCKET_NAME,
            key,
            Fields={"Content-Type": "application/zip"},
            Conditions=[{"Content-Type": "application/zip"}, ["content-length-range", 1, 524_288_000]],
            ExpiresIn=600,
        )
        public_endpoint = getattr(settings, "AWS_S3_PUBLIC_ENDPOINT_URL", "")
        if public_endpoint:
            signed_parts = urlsplit(signed["url"])
            public_parts = urlsplit(public_endpoint)
            signed["url"] = urlunsplit(
                (public_parts.scheme, public_parts.netloc, signed_parts.path, signed_parts.query, signed_parts.fragment)
            )
        return Response({"url": signed["url"], "fields": signed["fields"], "key": key})


class CourseViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CourseSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        return Course.objects.filter(owner=self.request.user).prefetch_related("lectures")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class LectureSlidesView(ListAPIView):
    serializer_class = SlideSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Slide.objects.none()
        lecture = get_object_or_404(Lecture, pk=self.kwargs["lecture_id"], course__owner=self.request.user)
        return Slide.objects.filter(lecture=lecture)
