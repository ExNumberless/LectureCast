from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q

from courses.models import Course, Lecture


class StageNode(models.Model):
    """The current output and state of one stage for a course or lecture."""

    class Stage(models.TextChoices):
        FETCH = "fetch", "Fetch course website"
        UPLOAD = "upload", "Import course archive"
        REVIEW = "review", "Review lecture list"
        MATERIALS = "materials", "Prepare lecture materials"
        TRANSCRIPT = "transcript", "Write transcript"
        TTS = "tts", "Synthesize narration"
        RENDER = "render", "Render slides"
        ASSEMBLE = "assemble", "Assemble slideshow"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        STALE = "stale", "Stale"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="stage_nodes")
    stage = models.CharField(max_length=32, choices=Stage.choices)
    lecture = models.ForeignKey(Lecture, null=True, blank=True, on_delete=models.CASCADE, related_name="stage_nodes")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    settings_hash = models.CharField(max_length=64, blank=True)
    inputs_hash = models.CharField(max_length=64, blank=True)
    output_prefix = models.CharField(max_length=512, blank=True)
    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pipeline_nodes_run"
    )
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pipeline_nodes_edited"
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    frozen = models.BooleanField(default=False)
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pipeline_nodes_claimed",
    )
    claim_expires = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["course_id", "stage", "lecture_id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["course", "stage"], condition=Q(lecture__isnull=True), name="unique_course_stage_node"
            ),
            models.UniqueConstraint(
                fields=["lecture", "stage"], condition=Q(lecture__isnull=False), name="unique_lecture_stage_node"
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["course", "status"], name="pipeline_course_status_idx"),
            models.Index(fields=["status", "updated_at"], name="pipeline_status_updated_idx"),
        ]

    def __str__(self):
        scope = f"lecture {self.lecture_id}" if self.lecture_id else f"course {self.course_id}"
        return f"{self.stage} for {scope} ({self.status})"


class PipelineRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="pipeline_runs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pipeline_runs")
    targets = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    estimate = models.JSONField(default=dict, blank=True)
    actual_usage = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at", "-id"]

    def __str__(self):
        return f"Run {self.pk} for {self.course} ({self.status})"


class StageRun(models.Model):
    class Status(models.TextChoices):
        BLOCKED = "blocked", "Waiting for dependencies"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Already up to date"

    run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="stage_runs")
    node = models.ForeignKey(StageNode, on_delete=models.CASCADE, related_name="stage_runs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.BLOCKED)
    progress = models.JSONField(default=dict, blank=True)
    log = models.JSONField(default=list, blank=True)
    usage = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["run", "node"], name="unique_stage_run_per_pipeline_run")
        ]

    def __str__(self):
        return f"Run {self.run_id}: {self.node}"
