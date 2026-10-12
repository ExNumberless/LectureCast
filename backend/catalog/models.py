from typing import ClassVar

from django.conf import settings
from django.db import models

from courses.models import Course
from pipeline.models import StageNode

# Licenses the catalog accepts. Rules for other licenses are not settled yet, so they can't be published.
OPEN_LICENSES = {
    "CC0-1.0": "CC0 1.0 (public domain dedication)",
    "CC-BY-4.0": "CC BY 4.0",
    "CC-BY-SA-4.0": "CC BY-SA 4.0",
    "CC-BY-3.0": "CC BY 3.0",
    "CC-BY-SA-3.0": "CC BY-SA 3.0",
}


class Publication(models.Model):
    """A course's place in the shared catalog. Only its first publication is moderated."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for review"
        APPROVED = "approved", "Published"
        REJECTED = "rejected", "Not approved"
        UNPUBLISHED = "unpublished", "Unpublished by an admin"

    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name="publication")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    license = models.CharField(max_length=32, choices=sorted(OPEN_LICENSES.items()))
    attribution = models.TextField(help_text="Credit for the source and its authors, shown with the course.")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="publication_requests"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="publications_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-requested_at", "-id"]

    def __str__(self):
        return f"{self.course} ({self.status})"


class ContentReport(models.Model):
    """A user's report about a catalog course or one of its stages, for the moderation queue."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="reports")
    node = models.ForeignKey(StageNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="content_reports"
    )
    reason = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_resolved"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at", "-id"]

    def __str__(self):
        return f"Report {self.pk} on {self.course} ({self.status})"


class TakedownRequest(models.Model):
    """A rights holder's complaint. Anyone may file one, with or without an account."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        TAKEN_DOWN = "taken_down", "Taken down"
        DISMISSED = "dismissed", "Dismissed"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="takedown_requests")
    name = models.CharField(max_length=200)
    email = models.EmailField()
    details = models.TextField(help_text="The work claimed and why this course infringes it.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="takedowns_handled"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at", "-id"]

    def __str__(self):
        return f"Takedown {self.pk} on {self.course} ({self.status})"


def freeze_published_nodes(course: Course) -> int:
    """Published outputs are frozen: later changes to them happen in a fork."""
    return course.stage_nodes.filter(status=StageNode.Status.SUCCEEDED, frozen=False).update(frozen=True)


def is_published(course_id: int) -> bool:
    return Publication.objects.filter(course_id=course_id, status=Publication.Status.APPROVED).exists()
