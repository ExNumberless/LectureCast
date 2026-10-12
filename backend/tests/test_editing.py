import pytest
from django.core.files.storage import default_storage

from accounts.models import User
from pipeline.models import SectionEdit, StageNode
from pipeline.scheduler import create_run
from pipeline.sections import parse
from tests.test_pipeline import drain, fetch_and_review


def test_parse_keeps_text_outside_sections_and_round_trips():
    markdown = "# Lecture\n\nIntro\n## [3] First\n\nOne.\n\n## [4]   Second  \nTwo.\n"
    document = parse(markdown)
    assert document.preamble == "# Lecture\n\nIntro\n"
    assert [(section.n, section.title, section.text) for section in document.sections] == [
        (3, "First", "\nOne.\n\n"),
        (4, "Second", "Two.\n"),
    ]
    assert document.render() == markdown


@pytest.fixture
def lecture_nodes(course, user, queue, django_capture_on_commit_callbacks):
    first, _ = fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "assemble", [first.id])
    drain(queue, django_capture_on_commit_callbacks)
    return {node.stage: node for node in StageNode.objects.filter(course=course, lecture=first)}


def read(node):
    node.refresh_from_db()
    with default_storage.open(f"{node.output_prefix}/{node.stage}.md") as handle:
        return handle.read().decode()


@pytest.mark.django_db
def test_editing_a_section_keeps_the_original_and_marks_later_nodes_stale(api, lecture_nodes):
    transcript = lecture_nodes["transcript"]
    generated = transcript.output_prefix

    response = api.get(f"/api/nodes/{transcript.pk}/sections")
    assert response.status_code == 200
    body = response.json()
    assert body["editable"] is True
    assert [(section["n"], section["title"]) for section in body["sections"]] == [(1, "Overview"), (2, "Details")]
    original = body["sections"][1]["text"]

    response = api.put(f"/api/nodes/{transcript.pk}/sections/2", {"text": "Edited details."}, "application/json")
    assert response.status_code == 200
    body = response.json()
    assert body["edit"]["edited_by_email"] == "owner@example.com"
    assert sorted(node["stage"] for node in body["stale_nodes"]) == ["assemble", "tts"]

    statuses = {node.stage: StageNode.objects.get(pk=node.pk).status for node in lecture_nodes.values()}
    assert statuses == {
        "materials": StageNode.Status.SUCCEEDED,
        "transcript": StageNode.Status.SUCCEEDED,
        "render": StageNode.Status.SUCCEEDED,
        "tts": StageNode.Status.STALE,
        "assemble": StageNode.Status.STALE,
    }

    edited = read(transcript)
    assert "## [2] Details\nEdited details.\n" in edited
    assert "Fake transcript for the overview" in edited
    assert transcript.generated_prefix == generated != transcript.output_prefix
    with default_storage.open(f"{generated}/transcript.md") as handle:
        assert original in handle.read().decode()

    sections = api.get(f"/api/nodes/{transcript.pk}/sections").json()["sections"]
    assert sections[1]["text"] == "Edited details.\n"
    assert sections[1]["original"] == original
    assert [edit["text"] for edit in sections[1]["edits"]] == ["Edited details.\n"]
    assert sections[0]["edits"] == [] and sections[0]["text"] == sections[0]["original"]


@pytest.mark.django_db
def test_saving_unchanged_text_does_nothing(api, lecture_nodes):
    materials = lecture_nodes["materials"]
    text = api.get(f"/api/nodes/{materials.pk}/sections").json()["sections"][0]["text"]

    response = api.put(f"/api/nodes/{materials.pk}/sections/1", {"text": text}, "application/json")

    assert response.json()["edit"] is None and response.json()["stale_nodes"] == []
    assert not SectionEdit.objects.exists()


@pytest.mark.django_db
def test_rerunning_a_stage_starts_from_fresh_output(
    api, course, user, queue, lecture_nodes, django_capture_on_commit_callbacks
):
    materials = lecture_nodes["materials"]
    api.put(f"/api/nodes/{materials.pk}/sections/1", {"text": "Mine."}, "application/json")
    StageNode.objects.filter(pk=materials.pk).update(status=StageNode.Status.STALE)

    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "materials", [materials.lecture_id])
    drain(queue, django_capture_on_commit_callbacks)

    sections = api.get(f"/api/nodes/{materials.pk}/sections").json()["sections"]
    assert sections[0]["text"].startswith("\nFake materials") and sections[0]["edits"] == []


@pytest.mark.django_db
def test_edits_are_refused_for_frozen_other_and_unknown_sections(api, client, lecture_nodes):
    transcript, tts = lecture_nodes["transcript"], lecture_nodes["tts"]

    assert api.get(f"/api/nodes/{tts.pk}/sections").status_code == 404
    assert api.put(f"/api/nodes/{transcript.pk}/sections/9", {"text": "x"}, "application/json").status_code == 404

    StageNode.objects.filter(pk=transcript.pk).update(frozen=True)
    body = api.get(f"/api/nodes/{transcript.pk}/sections").json()
    assert body["editable"] is False and "Fork" in body["reason"]
    assert api.put(f"/api/nodes/{transcript.pk}/sections/1", {"text": "x"}, "application/json").status_code == 400

    client.force_login(User.objects.create_user(email="stranger@example.com"))
    assert client.get(f"/api/nodes/{transcript.pk}/sections").status_code == 404
    assert client.put(f"/api/nodes/{transcript.pk}/sections/1", {"text": "x"}, "application/json").status_code == 404
