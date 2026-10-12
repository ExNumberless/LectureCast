"""Deterministic development stages used until the CSTL/STL adapters are integrated."""

import json
from pathlib import Path

from courses.models import Course

from .contracts import StageContext, StageResult


class FakeStageAdapter:
    def run(self, stage: str, context: StageContext, /) -> StageResult:
        context.output_dir.mkdir(parents=True, exist_ok=True)
        context.reporter.step(stage, 0, 1)
        context.reporter.log(f"Fake {stage} stage started.")

        if stage in {"fetch", "upload"}:
            course = Course.objects.get(pk=context.course_id)
            manifest = {
                "lectures": [
                    {
                        "number": 1,
                        "name": "lecture-01",
                        "title": f"{course.title}: Introduction",
                    },
                    {
                        "number": 2,
                        "name": "lecture-02",
                        "title": f"{course.title}: Core ideas",
                    },
                ]
            }
            output = context.output_dir / "lecture-list.json"
            output.write_text(json.dumps(manifest, indent=2) + "\n")
        elif stage in {"materials", "transcript"}:
            # Editable stages write Markdown with one "## [N] Title" section per slide.
            output = context.output_dir / f"{stage}.md"
            output.write_text(
                f"# {context.lecture}\n\n"
                f"## [1] Overview\n\nFake {stage} for the overview of {context.lecture}.\n\n"
                f"## [2] Details\n\nFake {stage} with math: $e^{{i\\pi}} + 1 = 0$.\n"
            )
        else:
            output = context.output_dir / "stage.json"
            output.write_text(
                json.dumps(
                    {
                        "stage": stage,
                        "course_id": context.course_id,
                        "lecture": context.lecture,
                        "settings": dict(context.settings),
                    },
                    indent=2,
                    default=str,
                )
                + "\n"
            )

        context.reporter.step(stage, 1, 1)
        context.reporter.log(f"Fake {stage} stage finished.")
        return StageResult(outputs=(Path(output.name),))
