import pytest
from django.test import Client

from accounts.models import User
from catalog.models import ContentReport, Publication, TakedownRequest
from courses.models import Course
from pipeline.models import StageNode
from pipeline.scheduler import create_run
from tests.test_pipeline import drain, fetch_and_review


@pytest.fixture
def admin_client(db):
    # A separate client, so the owner's `api` session stays signed in.
    admin = User.objects.create_user(email="admin@example.com", is_staff=True)
    staff = Client()
    staff.force_login(admin)
    return staff


@pytest.fixture
def reviewed(course, user, queue, django_capture_on_commit_callbacks):
    user.first_name, user.last_name = "Ada", "Lovelace"
    user.save()
    return fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)


def run(course, user, queue, capture, stage, lecture_ids=None):
    with capture(execute=True):
        create_run(course, user, stage, lecture_ids)
    drain(queue, capture)


def publish(api, course, license="CC-BY-4.0"):
    return api.post(
        f"/api/courses/{course.pk}/publication",
        {"license": license, "attribution": "Course notes by Prof. Example, Example University."},
        "application/json",
    )


@pytest.mark.django_db
def test_publication_needs_a_reviewed_course_and_an_open_license(api, course):
    response = publish(api, course)
    assert response.status_code == 400
    assert "Review the lecture list" in response.json()["course"]


@pytest.mark.django_db
def test_only_open_licenses_can_be_published(api, course, reviewed):
    response = publish(api, course, license="CC-BY-NC-SA-4.0")
    assert response.status_code == 400
    assert "open licenses" in str(response.json()["license"])
    assert not Publication.objects.exists()


@pytest.mark.django_db
def test_approval_freezes_outputs_and_only_admins_unpublish(
    api, admin_client, client, course, user, reviewed, queue, django_capture_on_commit_callbacks
):
    first, second = reviewed
    run(course, user, queue, django_capture_on_commit_callbacks, "tts", [first.id])

    response = publish(api, course)
    assert response.status_code == 201 and response.json()["status"] == "pending"
    assert publish(api, course).status_code == 400
    publication = Publication.objects.get()

    assert api.get("/api/moderation").status_code == 403
    queue_body = admin_client.get("/api/moderation").json()
    assert [item["id"] for item in queue_body["publications"]] == [publication.pk]

    response = admin_client.post(
        f"/api/moderation/publications/{publication.pk}", {"action": "approve"}, "application/json"
    )
    assert response.status_code == 200
    course.refresh_from_db()
    assert course.visibility == Course.Visibility.PUBLISHED and course.license == "CC-BY-4.0"
    succeeded = StageNode.objects.filter(course=course, status=StageNode.Status.SUCCEEDED)
    assert succeeded.exists() and all(node.frozen for node in succeeded)

    # Later outputs publish (and freeze) without another review.
    run(course, user, queue, django_capture_on_commit_callbacks, "materials", [second.id])
    assert StageNode.objects.get(course=course, stage="materials", lecture=second).frozen
    assert Publication.objects.get().status == Publication.Status.APPROVED

    # Owners can't unpublish; there is no owner endpoint for it, and the moderation API is staff only.
    assert (
        api.post(f"/api/moderation/publications/{publication.pk}", {"action": "unpublish"}, "application/json")
    ).status_code == 403
    response = admin_client.post(
        f"/api/moderation/publications/{publication.pk}",
        {"action": "unpublish", "note": "Rights unclear"},
        "application/json",
    )
    assert response.status_code == 200 and response.json()["status"] == "unpublished"
    assert not StageNode.objects.filter(course=course, frozen=True).exists()
    assert publish(api, course).status_code == 400


@pytest.mark.django_db
def test_rejected_courses_can_request_again(api, admin_client, course, reviewed):
    publish(api, course)
    publication = Publication.objects.get()
    admin_client.post(
        f"/api/moderation/publications/{publication.pk}", {"action": "reject", "note": "No"}, "application/json"
    )
    assert Publication.objects.get().status == Publication.Status.REJECTED
    assert not StageNode.objects.filter(course=course, frozen=True).exists()
    assert publish(api, course).json()["status"] == "pending"


@pytest.mark.django_db
def test_catalog_lists_playable_courses_with_coverage_and_credits(
    api, admin_client, client, course, user, reviewed, queue, django_capture_on_commit_callbacks
):
    first, second = reviewed
    run(course, user, queue, django_capture_on_commit_callbacks, "materials", [first.id])
    publish(api, course)
    admin_client.post(
        f"/api/moderation/publications/{Publication.objects.get().pk}", {"action": "approve"}, "application/json"
    )
    client.logout()

    assert client.get("/api/catalog").json() == []
    entries = client.get("/api/catalog?include_unplayable=true").json()
    assert [entry["id"] for entry in entries] == [course.pk]

    run(course, user, queue, django_capture_on_commit_callbacks, "tts", [first.id])
    (entry,) = client.get("/api/catalog").json()
    assert entry["license_name"] == "CC BY 4.0"
    assert entry["attribution"].startswith("Course notes by")
    assert entry["playable_lectures"] == 1
    assert entry["totals"] == {"materials": 1, "transcript": 1, "tts": 1, "render": 0, "assemble": 0}
    assert [(row["number"], row["stages"]) for row in entry["lectures"]] == [
        (first.number, ["materials", "transcript", "tts"]),
        (second.number, []),
    ]
    assert {"stage": "tts", "names": ["Ada Lovelace"]} in entry["contributors"]
    assert "owner@example.com" not in str(entry)
    assert client.get(f"/api/catalog/{course.pk}").json()["id"] == course.pk


@pytest.mark.django_db
def test_private_courses_stay_out_of_the_catalog(client, course, reviewed):
    assert client.get("/api/catalog?include_unplayable=true").json() == []
    assert client.get(f"/api/catalog/{course.pk}").status_code == 404


@pytest.mark.django_db
def test_reports_and_takedowns_reach_the_moderation_queue(api, admin_client, client, course, reviewed):
    publish(api, course)
    publication = Publication.objects.get()
    admin_client.post(f"/api/moderation/publications/{publication.pk}", {"action": "approve"}, "application/json")

    node = StageNode.objects.get(course=course, stage="fetch")
    response = api.post(
        f"/api/catalog/{course.pk}/reports", {"reason": "Wrong lecture order", "node": node.pk}, "application/json"
    )
    assert response.status_code == 201

    client.logout()
    response = client.post(
        "/api/catalog/takedowns",
        {"course": course.pk, "name": "Rights Holder", "email": "rights@example.com", "details": "My textbook."},
        "application/json",
    )
    assert response.status_code == 201

    body = admin_client.get("/api/moderation").json()
    assert [report["reason"] for report in body["reports"]] == ["Wrong lecture order"]
    assert [takedown["name"] for takedown in body["takedowns"]] == ["Rights Holder"]

    report = ContentReport.objects.get()
    admin_client.post(
        f"/api/moderation/reports/{report.pk}", {"action": "resolve", "note": "Fixed"}, "application/json"
    )
    takedown = TakedownRequest.objects.get()
    response = admin_client.post(
        f"/api/moderation/takedowns/{takedown.pk}", {"action": "take_down", "note": "Valid claim"}, "application/json"
    )
    assert response.json()["status"] == "taken_down"
    assert Publication.objects.get().status == Publication.Status.UNPUBLISHED
    assert admin_client.get("/api/moderation").json() == {"publications": [], "reports": [], "takedowns": []}


@pytest.mark.django_db
def test_takedowns_only_name_published_courses(client, course, reviewed):
    response = client.post(
        "/api/catalog/takedowns",
        {"course": course.pk, "name": "X", "email": "x@example.com", "details": "Mine."},
        "application/json",
    )
    assert response.status_code == 400
