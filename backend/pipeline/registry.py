from dataclasses import dataclass

from courses.models import Course

from .models import StageNode


@dataclass(frozen=True)
class StageDefinition:
    name: str
    scope: str
    dependencies: tuple[str, ...]
    capability: str
    queue: str
    is_gate: bool = False


STAGES = {
    "fetch": StageDefinition("fetch", "course", (), "scrape", "fetch"),
    "upload": StageDefinition("upload", "course", (), "scrape", "fetch"),
    "review": StageDefinition("review", "course", (), "scrape", "fetch", True),
    "materials": StageDefinition("materials", "lecture", ("review",), "scrape", "default"),
    "transcript": StageDefinition("transcript", "lecture", ("materials",), "transcribe", "default"),
    "tts": StageDefinition("tts", "lecture", ("transcript",), "narrate", "tts"),
    "render": StageDefinition("render", "lecture", ("materials",), "slideshow", "default"),
    "assemble": StageDefinition("assemble", "lecture", ("tts", "render"), "slideshow", "default"),
}


def source_stage(course: Course) -> str:
    return "upload" if course.provider in {Course.Provider.OCW, Course.Provider.FOLDER} else "fetch"


def dependencies_for(stage: str, course: Course) -> tuple[str, ...]:
    definition = STAGES[stage]
    if stage == "review":
        return (source_stage(course),)
    return definition.dependencies


def public_stage_registry(course: Course | None = None) -> list[dict[str, object]]:
    names = list(STAGES)
    if course is not None:
        names.remove("upload" if source_stage(course) == "fetch" else "fetch")
    return [
        {
            "name": name,
            "scope": STAGES[name].scope,
            "dependencies": list(dependencies_for(name, course)) if course else list(STAGES[name].dependencies),
            "capability": STAGES[name].capability,
            "queue": STAGES[name].queue,
            "is_gate": STAGES[name].is_gate,
        }
        for name in names
    ]


def stage_choices():
    return [(name, StageNode.Stage(name).label) for name in STAGES]
