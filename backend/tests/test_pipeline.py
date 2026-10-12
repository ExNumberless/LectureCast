import json
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from rest_framework.exceptions import ValidationError

from accounts.models import User
from courses.models import Course, Lecture
from pipeline import tasks
from pipeline.fake_stages import FakeStageAdapter
from pipeline.models import PipelineRun, StageNode, StageRun
from pipeline.registry import dependencies_for, public_stage_registry
from pipeline.scheduler import create_run, preview_run, sync_course_staleness, target_keys
from pipeline.workspace import hydrate_workspace, merge_course_cache, store_stage_outputs

LECTURE_STAGES = ["materials", "transcript", "tts", "render", "assemble"]


def drain(queue, capture):
    """Run every dispatched stage task, including those queued by finished stages."""
    order = []
    while queue:
        stage_run_id, celery_queue = queue.popleft()
        stage_run = StageRun.objects.select_related("node").get(pk=stage_run_id)
        order.append((stage_run.node.stage, stage_run.node.lecture_id, celery_queue))
        with capture(execute=True):
            tasks.execute_stage_run(stage_run_id)
    return order


def fetch_and_review(course, user, queue, capture):
    with capture(execute=True):
        create_run(course, user, "fetch")
    drain(queue, capture)
    review = StageNode.objects.get(course=course, stage="review")
    review.status = StageNode.Status.SUCCEEDED
    review.save()
    return list(course.lectures.order_by("number"))


def test_registry_swaps_source_stage_by_provider(user):
    website = Course(owner=user, title="Site", provider=Course.Provider.WEBSITE)
    ocw = Course(owner=user, title="OCW", provider=Course.Provider.OCW)

    assert dependencies_for("review", website) == ("fetch",)
    assert dependencies_for("review", ocw) == ("upload",)
    assert "upload" not in {stage["name"] for stage in public_stage_registry(website)}
    assert "fetch" not in {stage["name"] for stage in public_stage_registry(ocw)}
    assert {stage["name"] for stage in public_stage_registry()} >= {"fetch", "upload"}


@pytest.mark.django_db
def test_target_keys_are_in_dependency_order(course, user, queue, django_capture_on_commit_callbacks):
    lectures = fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)

    keys = [(stage, lecture.id if lecture else None) for stage, lecture in target_keys(course, "assemble")]

    assert keys[:2] == [("fetch", None), ("review", None)]
    for lecture in lectures:
        positions = {stage: keys.index((stage, lecture.id)) for stage in LECTURE_STAGES}
        assert positions["materials"] < positions["transcript"] < positions["tts"] < positions["assemble"]
        assert positions["materials"] < positions["render"] < positions["assemble"]
    assert len(keys) == len(set(keys)) == 2 + len(lectures) * len(LECTURE_STAGES)


@pytest.mark.django_db
def test_lecture_selection_is_validated(course, user, queue, django_capture_on_commit_callbacks):
    with pytest.raises(ValidationError, match="Review the course source"):
        target_keys(course, "materials")

    first, second = fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)

    selected = {lecture.id for _, lecture in target_keys(course, "transcript", [second.id]) if lecture}
    assert selected == {second.id}
    with pytest.raises(ValidationError, match="Select at least one lecture"):
        target_keys(course, "transcript", [])
    with pytest.raises(ValidationError, match="Course stages do not accept"):
        target_keys(course, "fetch", [first.id])
    with pytest.raises(ValidationError, match="does not match the course source"):
        target_keys(course, "upload")
    with pytest.raises(ValidationError, match="course review endpoint"):
        target_keys(course, "review")

    first.included = False
    first.save()
    with pytest.raises(ValidationError, match="not included"):
        target_keys(course, "transcript", [first.id])
    assert {lecture.id for _, lecture in target_keys(course, "transcript") if lecture} == {second.id}


@pytest.mark.django_db
def test_lecture_stages_need_a_reviewed_lecture_list(course, user, queue, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "fetch")
    drain(queue, django_capture_on_commit_callbacks)

    with pytest.raises(ValidationError, match="Review the fetched lecture list"):
        target_keys(course, "materials")


@pytest.mark.django_db
def test_fake_pipeline_runs_end_to_end(course, user, queue, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        fetch = create_run(course, user, "fetch")
    assert drain(queue, django_capture_on_commit_callbacks) == [("fetch", None, "fetch")]
    fetch.refresh_from_db()
    assert fetch.status == PipelineRun.Status.SUCCEEDED
    assert list(course.lectures.values_list("number", "name")) == [(1, "lecture-01"), (2, "lecture-02")]
    assert StageNode.objects.get(course=course, stage="review").status == StageNode.Status.PENDING

    fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        run = create_run(course, user, "assemble")
    order = drain(queue, django_capture_on_commit_callbacks)

    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.finished_at is not None
    statuses = dict(run.stage_runs.values_list("node__stage", "status").filter(node__lecture__isnull=True))
    assert statuses == {"fetch": StageRun.Status.SKIPPED, "review": StageRun.Status.SKIPPED}
    assert len(order) == 2 * len(LECTURE_STAGES)
    for lecture in course.lectures.all():
        stages = [stage for stage, lecture_id, _ in order if lecture_id == lecture.id]
        assert stages.index("materials") < stages.index("transcript") < stages.index("tts")
        assert stages.index("render") < stages.index("assemble") and stages.index("tts") < stages.index("assemble")
    assert {(stage, celery_queue) for stage, _, celery_queue in order if stage == "tts"} == {("tts", "tts")}

    assembled = StageNode.objects.filter(course=course, stage="assemble")
    assert all(node.status == StageNode.Status.SUCCEEDED for node in assembled)
    for node in assembled:
        with default_storage.open(f"{node.output_prefix}/stage.json") as handle:
            assert json.loads(handle.read())["stage"] == "assemble"
    stage_run = run.stage_runs.filter(node__stage="assemble").first()
    assert stage_run.progress == {"name": "assemble", "done": 1, "total": 1}
    assert [entry["message"] for entry in stage_run.log] == [
        "Fake assemble stage started.",
        "Fake assemble stage finished.",
    ]

    with django_capture_on_commit_callbacks(execute=True):
        rerun = create_run(course, user, "assemble")
    assert not queue
    rerun.refresh_from_db()
    assert rerun.status == PipelineRun.Status.SUCCEEDED
    assert set(rerun.stage_runs.values_list("status", flat=True)) == {StageRun.Status.SKIPPED}


@pytest.mark.django_db
def test_failed_stage_skips_downstream_work(course, user, queue, django_capture_on_commit_callbacks, monkeypatch):
    fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)

    original_run = FakeStageAdapter.run

    def run(self, stage, context):
        if stage == "transcript":
            raise RuntimeError("model unavailable")
        return original_run(self, stage, context)

    monkeypatch.setattr(FakeStageAdapter, "run", run)
    lecture = course.lectures.order_by("number").first()
    with django_capture_on_commit_callbacks(execute=True):
        run_record = create_run(course, user, "assemble", [lecture.id])
    with pytest.raises(RuntimeError, match="model unavailable"):
        drain(queue, django_capture_on_commit_callbacks)
    drain(queue, django_capture_on_commit_callbacks)

    run_record.refresh_from_db()
    assert run_record.status == PipelineRun.Status.FAILED
    assert "model unavailable" in run_record.error
    statuses = dict(run_record.stage_runs.filter(node__lecture=lecture).values_list("node__stage", "status"))
    assert statuses["materials"] == StageRun.Status.SUCCEEDED
    assert statuses["transcript"] == StageRun.Status.FAILED
    assert statuses["tts"] == statuses["assemble"] == StageRun.Status.SKIPPED
    assert StageNode.objects.get(stage="transcript", lecture=lecture).status == StageNode.Status.FAILED


@pytest.mark.django_db
def test_settings_changes_mark_only_affected_nodes_stale(course, user, queue, django_capture_on_commit_callbacks):
    fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "assemble")
    drain(queue, django_capture_on_commit_callbacks)

    course.settings = {"tts_voice": "narrator-2"}
    course.save()
    sync_course_staleness(course)

    status = {
        stage: set(StageNode.objects.filter(course=course, stage=stage).values_list("status", flat=True))
        for stage in ["fetch", "review", *LECTURE_STAGES]
    }
    assert status["tts"] == {StageNode.Status.STALE}
    for stage in ["fetch", "review", "materials", "transcript", "render"]:
        assert status[stage] == {StageNode.Status.SUCCEEDED}, stage

    preview = preview_run(course, "assemble")
    actions = {node["stage"]: node["action"] for node in preview["nodes"]}
    assert actions["tts"] == "run" and actions["transcript"] == "reuse"

    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "assemble")
    rerun_stages = [stage for stage, _, _ in drain(queue, django_capture_on_commit_callbacks)]
    assert sorted(rerun_stages) == ["assemble", "assemble", "tts", "tts"]
    assert set(StageNode.objects.filter(course=course).values_list("status", flat=True)) == {StageNode.Status.SUCCEEDED}


@pytest.mark.django_db
def test_frozen_nodes_are_not_marked_stale(course, user, queue, django_capture_on_commit_callbacks):
    fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "transcript")
    drain(queue, django_capture_on_commit_callbacks)
    StageNode.objects.filter(course=course, stage="transcript").update(frozen=True)

    course.settings = {"lecture_model": "other-model"}
    course.save()
    sync_course_staleness(course)

    assert set(StageNode.objects.filter(stage="transcript").values_list("status", flat=True)) == {
        StageNode.Status.SUCCEEDED
    }


@pytest.mark.django_db
def test_running_stage_cannot_be_started_twice(course, user, queue, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "fetch")
    with pytest.raises(ValidationError, match="already running"):
        create_run(course, user, "fetch")


@pytest.mark.django_db
def test_workspace_hydrates_namespaced_ancestor_outputs(
    course, user, queue, django_capture_on_commit_callbacks, tmp_path
):
    first, _ = fetch_and_review(course, user, queue, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        create_run(course, user, "assemble", [first.id])
    drain(queue, django_capture_on_commit_callbacks)
    default_storage.save(f"courses/{course.pk}/cache/pages/index.html", ContentFile(b"<html></html>"))

    node = StageNode.objects.get(course=course, stage="assemble", lecture=first)
    input_dir, cache_dir = tmp_path / "input", tmp_path / "cache"
    hydrate_workspace(course, node, input_dir, cache_dir)

    files = sorted(path.relative_to(input_dir).as_posix() for path in input_dir.rglob("*") if path.is_file())
    scope = f"lecture-{first.id}"
    assert files == [
        "fetch/course/lecture-list.json",
        f"materials/{scope}/materials.md",
        f"render/{scope}/stage.json",
        f"transcript/{scope}/transcript.md",
        f"tts/{scope}/stage.json",
    ]
    assert (cache_dir / "pages" / "index.html").read_bytes() == b"<html></html>"


@pytest.mark.django_db
def test_shared_cache_entries_are_immutable(course, tmp_path):
    cache_dir = tmp_path / "cache"
    (cache_dir / "pages").mkdir(parents=True)
    (cache_dir / "pages" / "a.html").write_bytes(b"first")
    merge_course_cache(course, cache_dir)
    merge_course_cache(course, cache_dir)

    (cache_dir / "pages" / "b.html").write_bytes(b"second")
    merge_course_cache(course, cache_dir)
    assert default_storage.exists(f"courses/{course.pk}/cache/pages/b.html")

    (cache_dir / "pages" / "a.html").write_bytes(b"changed")
    with pytest.raises(ValueError, match="immutable"):
        merge_course_cache(course, cache_dir)
    with default_storage.open(f"courses/{course.pk}/cache/pages/a.html") as handle:
        assert handle.read() == b"first"


def test_stage_outputs_must_be_declared_and_inside_the_workspace(tmp_path):
    output_dir = tmp_path / "output"
    (output_dir / "slides").mkdir(parents=True)
    (output_dir / "slides" / "1.png").write_bytes(b"png")
    (output_dir / "notes.txt").write_text("notes")
    (output_dir / "undeclared.txt").write_text("ignored")

    written = store_stage_outputs(output_dir, "prefix/run", [Path("slides"), Path("notes.txt")])
    assert sorted(written) == ["notes.txt", "slides/1.png"]
    assert not default_storage.exists("prefix/run/undeclared.txt")

    with pytest.raises(ValueError, match="does not exist"):
        store_stage_outputs(output_dir, "prefix/run", [Path("missing.txt")])
    with pytest.raises(ValueError, match="relative"):
        store_stage_outputs(output_dir, "prefix/run", [Path("../escape.txt")])


@pytest.mark.django_db
def test_api_runs_review_and_graph(api, course, queue, django_capture_on_commit_callbacks):
    response = api.get("/api/pipeline")
    assert response.status_code == 200
    assert "assemble" in {stage["name"] for stage in response.json()}

    response = api.post(f"/api/courses/{course.pk}/review", {"lectures": [{"id": 1, "number": 1}]}, "application/json")
    assert response.status_code == 400

    with django_capture_on_commit_callbacks(execute=True):
        response = api.post(f"/api/courses/{course.pk}/runs", {"stage": "fetch"}, "application/json")
    assert response.status_code == 202
    run_id = response.json()["id"]
    drain(queue, django_capture_on_commit_callbacks)

    response = api.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["status"] == PipelineRun.Status.SUCCEEDED

    response = api.post(f"/api/courses/{course.pk}/estimate", {"stage": "transcript"}, "application/json")
    assert response.status_code == 400

    first, second = course.lectures.order_by("number")
    response = api.post(
        f"/api/courses/{course.pk}/review",
        {"lectures": [{"id": second.id, "number": 1, "title": "Renamed"}]},
        "application/json",
    )
    assert response.status_code == 200
    assert response.json()["review"]["status"] == StageNode.Status.SUCCEEDED
    assert {item["id"]: item["included"] for item in response.json()["lectures"]} == {second.id: True, first.id: False}

    response = api.post(f"/api/courses/{course.pk}/estimate", {"stage": "transcript"}, "application/json")
    assert response.status_code == 200
    assert response.json()["targets"] == {"stage": "transcript", "lecture_ids": [second.id]}
    assert {node["stage"]: node["action"] for node in response.json()["nodes"]} == {
        "fetch": "reuse",
        "review": "reuse",
        "materials": "run",
        "transcript": "run",
    }

    response = api.get(f"/api/courses/{course.pk}/graph")
    assert response.status_code == 200
    nodes = {node["stage"]: node for node in response.json()["nodes"]}
    assert set(nodes) == {"fetch", "review"}
    assert nodes["fetch"]["run_by_email"] == "owner@example.com"
    assert nodes["fetch"]["latest_run"]["status"] == StageRun.Status.SUCCEEDED
    assert nodes["fetch"]["latest_run"]["log"][-1]["message"] == "Fake fetch stage finished."
    assert nodes["review"]["latest_run"] is None
    assert Lecture.objects.get(pk=second.pk).title == "Renamed"


@pytest.mark.django_db
def test_api_hides_other_users_courses_and_runs(client, course, user, queue, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        run = create_run(course, user, "fetch")
    client.force_login(User.objects.create_user(email="stranger@example.com"))

    assert client.get(f"/api/courses/{course.pk}/graph").status_code == 404
    assert client.post(f"/api/courses/{course.pk}/runs", {"stage": "fetch"}, "application/json").status_code == 404
    assert client.get(f"/api/runs/{run.pk}").status_code == 404


@pytest.mark.django_db
def test_api_requires_authentication(client, course):
    assert client.get("/api/pipeline").status_code in {401, 403}
    assert client.get(f"/api/courses/{course.pk}/graph").status_code in {401, 403}
