import importlib
import json
import tempfile
from datetime import date
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import is_published
from courses.models import Course, Lecture

from .contracts import StageContext
from .models import StageNode, StageRun
from .scheduler import node_inputs_hash, node_settings_hash, refresh_course_runs, sync_course_staleness
from .workspace import hydrate_workspace, merge_course_cache, store_stage_outputs


class DatabaseReporter:
    def __init__(self, stage_run: StageRun):
        self.stage_run = stage_run

    def step(self, name: str, done: int, total: int) -> None:
        self.stage_run.progress = {"name": name, "done": done, "total": total}
        self.stage_run.save(update_fields=["progress"])

    def log(self, message: str) -> None:
        self.stage_run.log = [*self.stage_run.log, {"at": timezone.now().isoformat(), "message": message}]
        self.stage_run.save(update_fields=["log"])

    def usage(self, vendor: str, model: str, **counts) -> None:
        event = {"vendor": vendor, "model": model, **counts}
        self.stage_run.usage = [*self.stage_run.usage, event]
        self.stage_run.save(update_fields=["usage"])


def _stage_adapter():
    path = getattr(settings, "PIPELINE_STAGE_ADAPTER", "pipeline.fake_stages.FakeStageAdapter")
    module_name, class_name = path.rsplit(".", 1)
    adapter_class = getattr(importlib.import_module(module_name), class_name)
    return adapter_class()


def _sync_lecture_manifest(course: Course, output_dir: Path):
    manifest_path = output_dir / "lecture-list.json"
    if not manifest_path.exists():
        raise ValueError("The source stage must produce lecture-list.json for review.")
    data = json.loads(manifest_path.read_text())
    rows = data.get("lectures") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("The source stage returned no lectures to review.")
    numbers = [row.get("number") for row in rows if isinstance(row, dict)]
    if len(numbers) != len(rows) or any(not isinstance(number, int) or number < 1 for number in numbers):
        raise ValueError("Every lecture in lecture-list.json needs a positive integer number.")
    if len(numbers) != len(set(numbers)):
        raise ValueError("Lecture numbers in lecture-list.json must be unique.")
    for row in rows:
        number = row["number"]
        date_value = row.get("date")
        parsed_date = date.fromisoformat(date_value) if date_value else None
        lecture, created = Lecture.objects.get_or_create(
            course=course,
            number=number,
            defaults={
                "name": str(row.get("name", ""))[:255],
                "title": str(row.get("title", ""))[:500],
                "date": parsed_date,
                "included": True,
            },
        )
        if not created:
            lecture.name = str(row.get("name", lecture.name))[:255]
            lecture.title = str(row.get("title", lecture.title))[:500]
            lecture.date = parsed_date
            lecture.included = True
            lecture.save(update_fields=["name", "title", "date", "included"])


def _finish_failure(stage_run_id: int, message: str):
    with transaction.atomic():
        stage_run = StageRun.objects.select_for_update().select_related("node", "run").get(pk=stage_run_id)
        stage_run.status = StageRun.Status.FAILED
        stage_run.error = message[:4000]
        stage_run.finished_at = timezone.now()
        stage_run.save(update_fields=["status", "error", "finished_at"])
        node = stage_run.node
        node.status = StageNode.Status.FAILED
        node.error = message[:4000]
        node.save(update_fields=["status", "error", "updated_at"])
        run = stage_run.run
        run.error = message[:4000]
        run.save(update_fields=["error"])
        run.stage_runs.filter(status=StageRun.Status.BLOCKED).update(
            status=StageRun.Status.SKIPPED,
            error="Skipped because a required stage failed.",
            finished_at=timezone.now(),
        )
    refresh_course_runs(stage_run.run.course_id)


@shared_task(bind=True, acks_late=True, name="pipeline.execute_stage_run")
def execute_stage_run(self, stage_run_id: int):
    with transaction.atomic():
        stage_run = (
            StageRun.objects.select_for_update(of=("self",))
            .select_related("node__course", "node__lecture", "run")
            .get(pk=stage_run_id)
        )
        if stage_run.status != StageRun.Status.QUEUED:
            return
        stage_run.status = StageRun.Status.RUNNING
        stage_run.started_at = timezone.now()
        stage_run.save(update_fields=["status", "started_at"])
        node = stage_run.node
        node.status = StageNode.Status.RUNNING
        node.save(update_fields=["status", "updated_at"])

    course = stage_run.run.course
    node = stage_run.node
    reporter = DatabaseReporter(stage_run)
    try:
        with tempfile.TemporaryDirectory(prefix=f"lecturecast-{node.stage}-") as directory:
            workspace = Path(directory)
            input_dir = workspace / "input"
            output_dir = workspace / "output"
            cache_dir = workspace / "cache"
            input_dir.mkdir()
            output_dir.mkdir()
            cache_dir.mkdir()
            hydrate_workspace(course, node, input_dir, cache_dir)
            context = StageContext(
                input_dir=input_dir,
                output_dir=output_dir,
                reporter=reporter,
                lecture=(node.lecture.title or node.lecture.name) if node.lecture else None,
                settings=course.settings,
                course_id=course.pk,
                cache_dir=cache_dir,
            )
            result = _stage_adapter().run(node.stage, context)
            if node.stage in {"fetch", "upload"}:
                _sync_lecture_manifest(course, output_dir)
            merge_course_cache(course, cache_dir)
            output_prefix = f"courses/{course.pk}/nodes/{node.pk}/runs/{stage_run.pk}"
            store_stage_outputs(output_dir, output_prefix, result.outputs)

        with transaction.atomic():
            stage_run = (
                StageRun.objects.select_for_update(of=("self",))
                .select_related("node__course", "node__lecture")
                .get(pk=stage_run_id)
            )
            node = stage_run.node
            node.status = StageNode.Status.SUCCEEDED
            node.output_prefix = output_prefix
            node.generated_prefix = output_prefix
            node.error = ""
            node.settings_hash = node_settings_hash(course, node.stage, node.lecture)
            node.inputs_hash = node_inputs_hash(course, node.stage, node.lecture)
            # Later outputs of an approved catalog course publish, and so freeze, without moderation.
            node.frozen = node.frozen or is_published(course.pk)
            node.save()
            stage_run.status = StageRun.Status.SUCCEEDED
            stage_run.finished_at = timezone.now()
            stage_run.save(update_fields=["status", "finished_at"])
            if node.stage in {"fetch", "upload"}:
                StageNode.objects.get_or_create(
                    course=course,
                    stage="review",
                    lecture=None,
                    defaults={"status": StageNode.Status.PENDING},
                )
            sync_course_staleness(course)
            run = stage_run.run
            if stage_run.status == StageRun.Status.SUCCEEDED:
                run.refresh_from_db()
                run.actual_usage = [
                    {"stage_run_id": item.id, **event} for item in run.stage_runs.all() for event in item.usage
                ]
                run.save(update_fields=["actual_usage"])
        refresh_course_runs(course.pk)
    except Exception as error:  # Celery records the exception too; persist a safe stage error first.
        _finish_failure(stage_run_id, f"{type(error).__name__}: {error}")
        raise

    return {"stage_run_id": stage_run_id, "status": StageRun.Status.SUCCEEDED}
