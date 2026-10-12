import hashlib
import json
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from courses.models import Course, Lecture

from .models import PipelineRun, StageNode, StageRun
from .registry import STAGES, dependencies_for, source_stage


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


_SETTINGS_BY_STAGE = {
    "fetch": {"site_columns"},
    "upload": set(),
    "review": set(),
    "materials": {"site_columns"},
    "transcript": {"course", "audience", "relevance", "lecture_model"},
    "tts": {"tts_voice"},
    "render": {"render_model", "slide_layout"},
    "assemble": set(),
}


def node_settings_hash(course: Course, stage: str, lecture: Lecture | None = None) -> str:
    settings = course.settings or {}
    stage_settings = {key: settings[key] for key in _SETTINGS_BY_STAGE[stage] if key in settings}
    return _json_hash(
        {
            "stage": stage,
            "provider": course.provider if stage in {"fetch", "upload", "materials"} else None,
            "plugin": course.plugin
            if stage in {"fetch", "upload", "materials", "transcript", "tts", "render"}
            else None,
            "course_title": course.title if stage in {"fetch", "upload", "transcript"} else None,
            "settings": stage_settings,
            "lecture": (
                {
                    "number": lecture.number,
                    "name": lecture.name,
                    "title": lecture.title,
                    "date": lecture.date,
                    "included": lecture.included,
                }
                if lecture
                else None
            ),
        }
    )


def _upstream_node(course: Course, stage: str, lecture: Lecture | None) -> StageNode | None:
    return StageNode.objects.filter(course=course, stage=stage, lecture=lecture).first()


def node_inputs_hash(course: Course, stage: str, lecture: Lecture | None) -> str:
    inputs = []
    for dependency in dependencies_for(stage, course):
        lecture_scoped = STAGES[dependency].scope == "lecture"
        upstream = _upstream_node(course, dependency, lecture if lecture_scoped else None)
        inputs.append(
            {
                "stage": dependency,
                "lecture_id": upstream.lecture_id if upstream else None,
                "settings_hash": upstream.settings_hash if upstream else None,
                "inputs_hash": upstream.inputs_hash if upstream else None,
                "output_prefix": upstream.output_prefix if upstream else None,
                "status": upstream.status if upstream else "missing",
            }
        )
    return _json_hash(inputs)


def sync_course_staleness(course: Course) -> None:
    """Mark completed nodes stale when their settings or upstream output has changed."""
    order = {
        name: index
        for index, name in enumerate(
            ("fetch", "upload", "review", "materials", "transcript", "tts", "render", "assemble")
        )
    }
    nodes = sorted(
        course.stage_nodes.select_related("lecture"), key=lambda node: (order[node.stage], node.lecture_id or 0)
    )
    for node in nodes:
        if node.frozen:
            continue
        new_settings_hash = node_settings_hash(course, node.stage, node.lecture)
        new_inputs_hash = node_inputs_hash(course, node.stage, node.lecture)
        changed = node.settings_hash != new_settings_hash or node.inputs_hash != new_inputs_hash
        if changed and node.status == StageNode.Status.SUCCEEDED:
            node.status = StageNode.Status.STALE
        if node.settings_hash != new_settings_hash or node.inputs_hash != new_inputs_hash or changed:
            node.settings_hash = new_settings_hash
            node.inputs_hash = new_inputs_hash
            node.save(update_fields=["settings_hash", "inputs_hash", "status", "updated_at"])


def _normalise_lecture_ids(course: Course, stage: str, lecture_ids: Iterable[int] | None) -> list[Lecture | None]:
    if STAGES[stage].scope == "course":
        if lecture_ids:
            raise ValidationError({"lecture_ids": "Course stages do not accept lecture selections."})
        return [None]
    if lecture_ids is None:
        return list(course.lectures.filter(included=True).order_by("number", "id"))
    ids = list(dict.fromkeys(lecture_ids))
    if not ids:
        raise ValidationError({"lecture_ids": "Select at least one lecture."})
    lectures = list(course.lectures.filter(included=True, id__in=ids).order_by("number", "id"))
    if {lecture.id for lecture in lectures} != set(ids):
        raise ValidationError({"lecture_ids": "One or more selected lectures are not included in this course."})
    return lectures


def target_keys(
    course: Course, stage: str, lecture_ids: Iterable[int] | None = None
) -> list[tuple[str, Lecture | None]]:
    if stage not in STAGES:
        raise ValidationError({"stage": "Choose a valid pipeline stage."})
    if STAGES[stage].is_gate:
        raise ValidationError({"stage": "Review the lecture list through the course review endpoint."})
    if stage in {"fetch", "upload"} and stage != source_stage(course):
        raise ValidationError({"stage": "This stage does not match the course source type."})

    selected = _normalise_lecture_ids(course, stage, lecture_ids)
    if STAGES[stage].scope == "lecture" and not selected:
        raise ValidationError({"lecture_ids": "Review the course source and add lectures before running this stage."})

    result: list[tuple[str, Lecture | None]] = []
    seen: set[tuple[str, int | None]] = set()

    def add(current_stage: str, lecture: Lecture | None):
        key = (current_stage, lecture.id if lecture else None)
        if key in seen:
            return
        for dependency in dependencies_for(current_stage, course):
            if STAGES[dependency].scope == "lecture":
                if lecture is None:
                    raise ValidationError({"stage": "A lecture-scoped dependency needs a lecture selection."})
                add(dependency, lecture)
            else:
                add(dependency, None)
        seen.add(key)
        result.append((current_stage, lecture))

    for lecture in selected:
        add(stage, lecture)

    if any(name not in {source_stage(course), "review"} for name, _ in result):
        review = _upstream_node(course, "review", None)
        if review is None or review.status != StageNode.Status.SUCCEEDED:
            raise ValidationError({"stage": "Review the fetched lecture list before running lecture stages."})
    return result


def preview_run(course: Course, stage: str, lecture_ids: Iterable[int] | None = None) -> dict[str, object]:
    keys = target_keys(course, stage, lecture_ids)
    existing = {(node.stage, node.lecture_id): node for node in course.stage_nodes.select_related("lecture").all()}
    nodes = []
    for name, lecture in keys:
        node = existing.get((name, lecture.id if lecture else None))
        fresh = node is not None and node.status == StageNode.Status.SUCCEEDED and not node.frozen
        nodes.append(
            {
                "stage": name,
                "lecture_id": lecture.id if lecture else None,
                "lecture_title": lecture.title if lecture else None,
                "status": node.status if node else StageNode.Status.PENDING,
                "action": "reuse" if fresh else "run",
            }
        )
    return {
        "targets": {
            "stage": stage,
            "lecture_ids": [lecture.id for lecture in _normalise_lecture_ids(course, stage, lecture_ids) if lecture],
        },
        "nodes": nodes,
        "estimate": {"available": False, "reason": "Cost estimates are not enabled yet."},
    }


def create_run(course: Course, user, stage: str, lecture_ids: Iterable[int] | None = None) -> PipelineRun:
    with transaction.atomic():
        course = Course.objects.select_for_update().get(pk=course.pk)
        sync_course_staleness(course)
        keys = target_keys(course, stage, lecture_ids)
        selected_lectures = _normalise_lecture_ids(course, stage, lecture_ids)
        target = {
            "stage": stage,
            "lecture_ids": [lecture.id for lecture in selected_lectures if lecture is not None],
        }
        run = PipelineRun.objects.create(
            course=course,
            requested_by=user,
            targets=[target],
            estimate={"available": False, "reason": "Cost estimates are not enabled yet."},
        )
        for name, lecture in keys:
            node, _ = StageNode.objects.get_or_create(
                course=course,
                stage=name,
                lecture=lecture,
                defaults={
                    "status": StageNode.Status.PENDING,
                    "settings_hash": node_settings_hash(course, name, lecture),
                    "inputs_hash": node_inputs_hash(course, name, lecture),
                },
            )
            if node.frozen and node.status != StageNode.Status.SUCCEEDED:
                raise ValidationError({"stage": f"The frozen {name} output cannot be rerun."})
            if node.status in {StageNode.Status.QUEUED, StageNode.Status.RUNNING}:
                raise ValidationError({"stage": f"The {name} stage is already running."})
            if node.status == StageNode.Status.SUCCEEDED and not node.frozen:
                node.status = (
                    StageNode.Status.STALE
                    if (
                        node.settings_hash != node_settings_hash(course, name, lecture)
                        or node.inputs_hash != node_inputs_hash(course, name, lecture)
                    )
                    else StageNode.Status.SUCCEEDED
                )
            if node.status == StageNode.Status.SUCCEEDED:
                StageRun.objects.create(run=run, node=node, status=StageRun.Status.SKIPPED)
                continue
            node.status = StageNode.Status.PENDING
            node.error = ""
            node.run_by = user
            node.settings_hash = node_settings_hash(course, name, lecture)
            node.inputs_hash = node_inputs_hash(course, name, lecture)
            node.save()
            StageRun.objects.create(run=run, node=node, status=StageRun.Status.BLOCKED)

        transaction.on_commit(lambda: enqueue_ready_nodes(run.id))
        return run


def enqueue_ready_nodes(run_id: int) -> None:
    """Queue nodes whose direct upstream nodes have succeeded."""
    from .tasks import execute_stage_run

    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().select_related("course").get(pk=run_id)
        if run.status in {PipelineRun.Status.FAILED, PipelineRun.Status.CANCELED, PipelineRun.Status.SUCCEEDED}:
            return
        queued_tasks = []
        for stage_run in run.stage_runs.select_for_update(of=("self",)).select_related("node__lecture"):
            if stage_run.status != StageRun.Status.BLOCKED or STAGES[stage_run.node.stage].is_gate:
                continue
            ready = True
            for dependency in dependencies_for(stage_run.node.stage, run.course):
                dep_lecture = stage_run.node.lecture if STAGES[dependency].scope == "lecture" else None
                upstream = _upstream_node(run.course, dependency, dep_lecture)
                if upstream is None or upstream.status != StageNode.Status.SUCCEEDED:
                    ready = False
                    break
            if ready:
                stage_run.status = StageRun.Status.QUEUED
                stage_run.save(update_fields=["status"])
                stage_run.node.status = StageNode.Status.QUEUED
                stage_run.node.save(update_fields=["status", "updated_at"])
                queued_tasks.append((stage_run.id, STAGES[stage_run.node.stage].queue))

        if queued_tasks:
            run.status = PipelineRun.Status.RUNNING
            run.started_at = run.started_at or timezone.now()
            run.save(update_fields=["status", "started_at"])
            for stage_run_id, queue in queued_tasks:
                transaction.on_commit(
                    lambda stage_run_id=stage_run_id, queue=queue: execute_stage_run.apply_async(
                        args=(stage_run_id,), queue=queue
                    )
                )
        else:
            _refresh_run_status(run)


def refresh_course_runs(course_id: int) -> None:
    run_ids = PipelineRun.objects.filter(
        course_id=course_id, status__in=[PipelineRun.Status.PENDING, PipelineRun.Status.RUNNING]
    ).values_list("id", flat=True)
    for run_id in run_ids:
        enqueue_ready_nodes(run_id)


def _refresh_run_status(run: PipelineRun):
    statuses = list(run.stage_runs.values_list("status", flat=True))
    active = {StageRun.Status.BLOCKED, StageRun.Status.QUEUED, StageRun.Status.RUNNING}
    if any(status in active for status in statuses):
        run.status = (
            PipelineRun.Status.RUNNING
            if any(status in {StageRun.Status.QUEUED, StageRun.Status.RUNNING} for status in statuses)
            else PipelineRun.Status.PENDING
        )
    elif run.error or any(status == StageRun.Status.FAILED for status in statuses):
        run.status = PipelineRun.Status.FAILED
        run.finished_at = run.finished_at or timezone.now()
    elif not statuses or all(status in {StageRun.Status.SUCCEEDED, StageRun.Status.SKIPPED} for status in statuses):
        run.status = PipelineRun.Status.SUCCEEDED
        run.finished_at = run.finished_at or timezone.now()
    else:
        run.status = PipelineRun.Status.PENDING
    run.save(update_fields=["status", "finished_at"])
