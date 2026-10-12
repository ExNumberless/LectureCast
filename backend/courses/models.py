from typing import ClassVar
from uuid import uuid4

from django.conf import settings
from django.db import models


def course_source_upload_to(_instance, filename):
    return f"course-sources/{uuid4()}/{filename}"


class Course(models.Model):
    class Provider(models.TextChoices):
        WEBSITE = "website", "Course website"
        OCW = "ocw", "MIT OpenCourseWare"
        FOLDER = "folder", "Folder upload"

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        PUBLISHED = "published", "Published"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses")
    title = models.CharField(max_length=255)
    source_url = models.URLField(blank=True)
    source_file = models.FileField(upload_to=course_source_upload_to, blank=True)
    provider = models.CharField(max_length=32, choices=Provider.choices)
    plugin = models.CharField(max_length=100, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    license = models.CharField(max_length=100, blank=True)
    visibility = models.CharField(max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="forks")
    forked_at_stage = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-updated_at", "id"]

    def __str__(self):
        return self.title


class Lecture(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lectures")
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=500, blank=True)
    date = models.DateField(null=True, blank=True)
    audio = models.FileField(upload_to="lectures/audio/", blank=True)
    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["number", "id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["course", "number"], name="unique_lecture_number_per_course")
        ]

    def __str__(self):
        return self.title or self.name or f"Lecture {self.number}"


class Slide(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        MARKDOWN = "markdown", "Markdown"
        CODE = "code", "Code"

    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name="slides")
    n = models.PositiveIntegerField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=500, blank=True)
    image = models.FileField(upload_to="lectures/slides/", blank=True)
    markdown = models.TextField(blank=True)
    code = models.TextField(blank=True)
    language = models.CharField(max_length=64, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    narration = models.TextField(blank=True)
    start_ms = models.PositiveBigIntegerField(null=True, blank=True)
    end_ms = models.PositiveBigIntegerField(null=True, blank=True)
    source = models.TextField(blank=True)
    locator = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["n", "id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["lecture", "n"], name="unique_slide_number_per_lecture")
        ]

    def __str__(self):
        return self.title or f"Slide {self.n}"
