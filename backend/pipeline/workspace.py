import hashlib
from pathlib import Path, PurePosixPath

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from courses.models import Course

from .models import StageNode


def _walk_storage(prefix: str):
    """Yield (key, relative path) pairs below a storage prefix."""
    prefix = prefix.rstrip("/")
    if not prefix:
        return
    stack = [(prefix, PurePosixPath())]
    while stack:
        current, relative = stack.pop()
        try:
            directories, files = default_storage.listdir(current)
        except FileNotFoundError:
            continue
        for filename in files:
            rel = relative / filename
            yield f"{current}/{filename}", rel
        for directory in directories:
            stack.append((f"{current}/{directory}", relative / directory))


def _safe_relative(path: Path | PurePosixPath) -> Path:
    value = Path(*path.parts)
    if value.is_absolute() or not value.parts or any(part in {"", ".", ".."} for part in value.parts):
        raise ValueError("Workspace paths must be relative and stay inside the workspace")
    return value


def _download_prefix(prefix: str, destination: Path):
    for key, relative in _walk_storage(prefix) or ():
        target = destination / _safe_relative(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with default_storage.open(key, "rb") as source:
            target.write_bytes(source.read())


def _local_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Stage workspaces cannot contain symbolic links")
        if path.is_file():
            yield path, _safe_relative(path.relative_to(root))


def hydrate_workspace(course: Course, node: StageNode, input_dir: Path, cache_dir: Path):
    """Download upstream stage outputs into namespaced folders and restore the shared cache."""
    ancestors = _ancestors(node)
    for ancestor in ancestors:
        if ancestor.output_prefix:
            scope = f"lecture-{ancestor.lecture_id}" if ancestor.lecture_id else "course"
            _download_prefix(ancestor.output_prefix, input_dir / ancestor.stage / scope)

    if course.source_file:
        source = input_dir / "source.zip"
        source.parent.mkdir(parents=True, exist_ok=True)
        with course.source_file.open("rb") as handle:
            source.write_bytes(handle.read())

    _download_prefix(f"courses/{course.pk}/cache", cache_dir)


def _ancestors(node: StageNode) -> list[StageNode]:
    from .registry import dependencies_for

    found: dict[int, StageNode] = {}
    stack = [(node.stage, node.lecture)]
    while stack:
        stage, lecture = stack.pop()
        for dependency in dependencies_for(stage, node.course):
            definition_is_lecture = dependency in {"materials", "transcript", "tts", "render", "assemble"}
            dependency_lecture = lecture if definition_is_lecture else None
            upstream = StageNode.objects.filter(
                course=node.course, stage=dependency, lecture=dependency_lecture
            ).first()
            if upstream is not None and upstream.pk not in found:
                found[upstream.pk] = upstream
                stack.append((upstream.stage, upstream.lecture))
    order = {
        name: index
        for index, name in enumerate(
            ("fetch", "upload", "review", "materials", "transcript", "tts", "render", "assemble")
        )
    }
    return sorted(found.values(), key=lambda item: (order[item.stage], item.lecture_id or 0, item.pk))


def store_stage_outputs(output_dir: Path, prefix: str, outputs):
    """Upload only declared stage files beneath a unique, run-specific prefix."""
    written = []
    files = []
    for output in outputs:
        relative_output = _safe_relative(output)
        path = output_dir / relative_output
        if path.is_symlink() or not path.exists():
            raise ValueError(f"Declared stage output does not exist: {relative_output}")
        if path.is_dir():
            files.extend(
                (child, relative_output / child_relative) for child, child_relative in (_local_files(path) or ())
            )
        elif path.is_file():
            files.append((path, relative_output))
        else:
            raise ValueError(f"Declared stage output is not a file or directory: {relative_output}")
    for path, relative in files:
        key = f"{prefix.rstrip('/')}/{relative.as_posix()}"
        with path.open("rb") as source:
            saved = default_storage.save(key, ContentFile(source.read()))
        if saved != key:
            default_storage.delete(saved)
            raise RuntimeError("Storage changed a stage output key unexpectedly")
        written.append(relative.as_posix())
    return written


def merge_course_cache(course: Course, cache_dir: Path):
    """Merge cache additions without ever overwriting an existing shared cache entry."""
    prefix = f"courses/{course.pk}/cache"
    with transaction.atomic():
        Course.objects.select_for_update().get(pk=course.pk)
        for path, relative in _local_files(cache_dir) or ():
            key = f"{prefix}/{relative.as_posix()}"
            data = path.read_bytes()
            if default_storage.exists(key):
                with default_storage.open(key, "rb") as existing:
                    current = existing.read()
                if current != data:
                    digest = hashlib.sha256(current).hexdigest()
                    raise ValueError(f"Cache entry {relative.as_posix()} is immutable (existing sha256 {digest})")
                continue
            saved = default_storage.save(key, ContentFile(data))
            if saved != key:
                default_storage.delete(saved)
                raise RuntimeError("Storage changed a shared cache key unexpectedly")
