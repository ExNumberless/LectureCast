from collections import defaultdict

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from courses.models import Course
from pipeline.models import StageNode

from .models import OPEN_LICENSES, ContentReport, Publication, TakedownRequest, freeze_published_nodes

COVERAGE_STAGES = ("materials", "transcript", "tts", "render", "assemble")


def request_publication(course: Course, user, license: str, attribution: str) -> Publication:
    """Ask to publish a course. Allowed at any stage after the lecture list is reviewed."""
    with transaction.atomic():
        course = Course.objects.select_for_update().get(pk=course.pk)
        review = course.stage_nodes.filter(stage="review", lecture__isnull=True).first()
        if review is None or review.status != StageNode.Status.SUCCEEDED:
            raise ValidationError({"course": "Review the lecture list before publishing."})
        publication = Publication.objects.filter(course=course).first()
        if publication and publication.status in {Publication.Status.APPROVED, Publication.Status.PENDING}:
            raise ValidationError({"course": f"This course is already {publication.get_status_display().lower()}."})
        if publication and publication.status == Publication.Status.UNPUBLISHED:
            raise ValidationError({"course": "An admin unpublished this course. Contact support to publish it again."})
        if license not in OPEN_LICENSES:
            raise ValidationError({"license": "The catalog only accepts open licenses."})
        publication = publication or Publication(course=course)
        publication.status = Publication.Status.PENDING
        publication.license = license
        publication.attribution = attribution
        publication.requested_by = user
        publication.reviewed_by = None
        publication.reviewed_at = None
        publication.review_note = ""
        publication.save()
        course.license = license
        course.save(update_fields=["license", "updated_at"])
        return publication


def _set_visibility(course: Course, visibility: str):
    course.visibility = visibility
    course.save(update_fields=["visibility", "updated_at"])


def moderate_publication(publication: Publication, admin, action: str, note: str) -> Publication:
    with transaction.atomic():
        publication = Publication.objects.select_for_update().select_related("course").get(pk=publication.pk)
        course = publication.course
        if action == "approve":
            if publication.status != Publication.Status.PENDING:
                raise ValidationError({"action": "Only pending publications can be approved."})
            publication.status = Publication.Status.APPROVED
            _set_visibility(course, Course.Visibility.PUBLISHED)
            freeze_published_nodes(course)
        elif action == "reject":
            if publication.status != Publication.Status.PENDING:
                raise ValidationError({"action": "Only pending publications can be rejected."})
            publication.status = Publication.Status.REJECTED
        elif action == "unpublish":
            if publication.status != Publication.Status.APPROVED:
                raise ValidationError({"action": "Only published courses can be unpublished."})
            unpublish(publication)
        else:
            raise ValidationError({"action": "Choose approve, reject or unpublish."})
        publication.reviewed_by = admin
        publication.reviewed_at = timezone.now()
        publication.review_note = note
        publication.save()
        return publication


def unpublish(publication: Publication):
    """Remove a course from the catalog. Its outputs unfreeze so the owner can work on them again."""
    publication.status = Publication.Status.UNPUBLISHED
    _set_visibility(publication.course, Course.Visibility.PRIVATE)
    publication.course.stage_nodes.update(frozen=False)


def resolve_report(report: ContentReport, admin, note: str) -> ContentReport:
    if report.status != ContentReport.Status.OPEN:
        raise ValidationError({"action": "This report is already resolved."})
    report.status = ContentReport.Status.RESOLVED
    report.resolved_by = admin
    report.resolved_at = timezone.now()
    report.resolution = note
    report.save()
    return report


def handle_takedown(takedown: TakedownRequest, admin, action: str, note: str) -> TakedownRequest:
    with transaction.atomic():
        takedown = TakedownRequest.objects.select_for_update().get(pk=takedown.pk)
        if takedown.status != TakedownRequest.Status.OPEN:
            raise ValidationError({"action": "This takedown request is already handled."})
        if action == "take_down":
            publication = Publication.objects.select_for_update().filter(course_id=takedown.course_id).first()
            if publication and publication.status == Publication.Status.APPROVED:
                unpublish(publication)
                publication.reviewed_by = admin
                publication.reviewed_at = timezone.now()
                publication.review_note = f"Taken down: {note}".strip()
                publication.save()
            takedown.status = TakedownRequest.Status.TAKEN_DOWN
        elif action == "dismiss":
            takedown.status = TakedownRequest.Status.DISMISSED
        else:
            raise ValidationError({"action": "Choose take_down or dismiss."})
        takedown.handled_by = admin
        takedown.handled_at = timezone.now()
        takedown.note = note
        takedown.save()
        return takedown


def _display_name(user) -> str:
    # The catalog is public, so contributors are credited by name, never by email.
    return (user.get_full_name() if user else "") or "A LectureCast user"


def catalog_entry(publication: Publication) -> dict[str, object]:
    course = publication.course
    lectures = [lecture for lecture in course.lectures.all() if lecture.included]
    reached: dict[int, set[str]] = defaultdict(set)
    contributors: dict[str, set[str]] = defaultdict(set)
    for node in course.stage_nodes.all():
        if node.status != StageNode.Status.SUCCEEDED:
            continue
        if node.lecture_id is not None:
            reached[node.lecture_id].add(node.stage)
        contributors[node.stage].add(_display_name(node.run_by))

    rows = [
        {
            "number": lecture.number,
            "title": lecture.title or lecture.name,
            "stages": [stage for stage in COVERAGE_STAGES if stage in reached[lecture.id]],
        }
        for lecture in sorted(lectures, key=lambda item: (item.number, item.id))
    ]
    return {
        "id": course.pk,
        "title": course.title,
        "provider": course.provider,
        "source_url": course.source_url,
        "license": publication.license,
        "license_name": OPEN_LICENSES.get(publication.license, publication.license),
        "attribution": publication.attribution,
        "published_at": publication.reviewed_at,
        # Audio-only lectures count as playable.
        "playable_lectures": sum(1 for row in rows if {"tts", "assemble"} & set(row["stages"])),
        "totals": {stage: sum(1 for row in rows if stage in row["stages"]) for stage in COVERAGE_STAGES},
        "lectures": rows,
        "contributors": [
            {"stage": stage, "names": sorted(names)}
            for stage, names in contributors.items()
            if stage in COVERAGE_STAGES
        ],
    }
