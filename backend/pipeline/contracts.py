"""Stable interfaces shared by pipeline stages and their library adapters."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

StageName = Literal["fetch", "upload", "review", "materials", "transcript", "tts", "render", "assemble"]


class JobReporter(Protocol):
    """Progress and billable usage interface shared with CSTL and STL."""

    def step(self, name: str, done: int, total: int) -> None:
        """Report progress; done=0 starts a step and later calls advance it."""

    def log(self, message: str) -> None:
        """Report a user-visible log line."""

    def usage(
        self,
        vendor: str,
        model: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        characters: int = 0,
        requests: int = 1,
    ) -> None:
        """Report one vendor request and its billable usage."""


class WarningReporter(Protocol):
    def warn(self, message: str) -> None:
        """Report a non-fatal warning separately when supported."""


def report_warning(reporter: JobReporter, message: str) -> None:
    """Match CSTL's behavior: use warn() when available, otherwise log()."""
    warning = getattr(reporter, "warn", None)
    (warning if callable(warning) else reporter.log)(message)


@dataclass(frozen=True)
class StageContext:
    """Inputs passed to each stage, rooted in its isolated local workspace."""

    input_dir: Path
    output_dir: Path
    reporter: JobReporter
    lecture: str | None = None
    settings: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StageResult:
    """Files produced by a stage, relative to StageContext.output_dir."""

    outputs: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if any(path.is_absolute() or ".." in path.parts for path in self.outputs):
            raise ValueError("Stage outputs must stay within the stage output directory")


class StageFunction(Protocol):
    """Signature for a concrete or fake stage implementation."""

    def __call__(self, context: StageContext, /) -> StageResult: ...


class StageAdapter(Protocol):
    """Boundary between the scheduler and a concrete stage library."""

    def run(self, stage: StageName, context: StageContext, /) -> StageResult: ...
