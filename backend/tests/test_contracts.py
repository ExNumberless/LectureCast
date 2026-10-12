import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from pipeline.contracts import StageContext, StageResult, report_warning

FIXTURES = Path(__file__).parent / "fixtures"


def test_player_and_chapters_fixtures_share_section_numbers_and_times():
    player = json.loads((FIXTURES / "player.json").read_text())
    chapters = json.loads((FIXTURES / "chapters.json").read_text())
    schemas = [
        json.loads(path.read_text()) for path in (FIXTURES / "slides.schema.json", FIXTURES / "player.schema.json")
    ]
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas)
    player_schema = next(schema for schema in schemas if schema["title"] == "player.json")
    Draft202012Validator(player_schema, registry=registry).validate(player)

    assert [slide["n"] for slide in player["slides"]] == [chapter["n"] for chapter in chapters]
    for slide, chapter in zip(player["slides"], chapters, strict=True):
        assert set(chapter) == {"n", "title", "start_ms", "end_ms"}
        assert slide["title"] == chapter["title"]
        assert slide["start_ms"] == chapter["start_ms"]
        assert slide["end_ms"] == chapter["end_ms"]
        assert slide["narration"]


def test_stage_contract_has_isolated_paths_and_relative_outputs(tmp_path):
    class Reporter:
        def step(self, name, done, total):
            pass

        def log(self, message):
            pass

        def usage(self, vendor, model, **counts):
            pass

    context = StageContext(
        input_dir=tmp_path / "input", output_dir=tmp_path / "output", reporter=Reporter(), lecture="lecture-01"
    )
    result = StageResult(outputs=(Path("materials/lecture-01.md"),))

    assert context.lecture == "lecture-01"
    assert not result.outputs[0].is_absolute()

    with pytest.raises(ValueError, match="within the stage output directory"):
        StageResult(outputs=(Path("../outside.txt"),))


def test_report_warning_uses_warn_when_available_and_falls_back_to_log():
    messages = []

    class Reporter:
        def log(self, message):
            messages.append(("log", message))

        def warn(self, message):
            messages.append(("warn", message))

    class BasicReporter:
        def log(self, message):
            messages.append(("log", message))

    report_warning(Reporter(), "first")
    report_warning(BasicReporter(), "second")
    assert messages == [("warn", "first"), ("log", "second")]
