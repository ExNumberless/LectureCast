"""Section-by-section editing of `materials` and `transcript` Markdown output."""

import re
from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .models import SectionEdit, StageNode
from .scheduler import sync_course_staleness
from .workspace import _walk_storage

EDITABLE_STAGES = {"materials", "transcript"}
_HEADING = re.compile(r"^## \[(\d+)\][ \t]*(.*)$")


@dataclass
class Section:
    n: int
    title: str
    heading: str
    text: str


@dataclass
class Document:
    preamble: str
    sections: list[Section]

    def section(self, n: int) -> Section | None:
        return next((section for section in self.sections if section.n == n), None)

    def render(self) -> str:
        parts = [self.preamble] if self.preamble else []
        parts += [f"{section.heading}\n{section.text}" for section in self.sections]
        return "".join(parts)


def parse(markdown: str) -> Document:
    """Split Markdown into the text before the first `## [N] Title` heading and one section per heading."""
    preamble: list[str] = []
    sections: list[Section] = []
    for line in markdown.splitlines(keepends=True):
        match = _HEADING.match(line.rstrip("\r\n"))
        if match:
            sections.append(Section(int(match[1]), match[2].strip(), line.rstrip("\r\n"), ""))
        elif sections:
            sections[-1].text += line
        else:
            preamble.append(line)
    return Document("".join(preamble), sections)


def _document_key(prefix: str) -> str:
    """The node's editable document: the one Markdown file at the top of its output."""
    prefix = prefix.rstrip("/")
    keys = [key for key, relative in _walk_storage(prefix) if len(relative.parts) == 1 and relative.suffix == ".md"]
    if len(keys) != 1:
        raise NotFound("This stage's output has no single Markdown document to edit.")
    return keys[0]


def read_document(prefix: str) -> tuple[str, Document]:
    key = _document_key(prefix)
    with default_storage.open(key, "rb") as handle:
        return key, parse(handle.read().decode())


def edit_block_reason(node: StageNode) -> str | None:
    if node.stage not in EDITABLE_STAGES:
        return "Only materials and transcripts can be edited."
    if node.frozen:
        return "This output is frozen. Fork the course to change it."
    if node.status not in {StageNode.Status.SUCCEEDED, StageNode.Status.STALE} or not node.output_prefix:
        return "Run this stage before editing its output."
    return None


def node_sections(node: StageNode) -> list[dict[str, object]]:
    _, current = read_document(node.output_prefix)
    _, generated = read_document(node.generated_prefix or node.output_prefix)
    edits: dict[int, list[SectionEdit]] = {}
    for edit in node.section_edits.filter(generated_prefix=node.generated_prefix).select_related("edited_by"):
        edits.setdefault(edit.n, []).append(edit)
    result = []
    for section in current.sections:
        original = generated.section(section.n)
        result.append(
            {
                "n": section.n,
                "title": section.title,
                "text": section.text,
                "original": original.text if original else "",
                "edits": edits.get(section.n, []),
            }
        )
    return result


def _copy_prefix(source: str, destination: str, replace_key: str, replacement: bytes):
    for key, relative in _walk_storage(source):
        target = f"{destination}/{relative.as_posix()}"
        if key == replace_key:
            data = replacement
        else:
            with default_storage.open(key, "rb") as handle:
                data = handle.read()
        saved = default_storage.save(target, ContentFile(data))
        if saved != target:
            default_storage.delete(saved)
            raise RuntimeError("Storage changed an edited output key unexpectedly")


def save_section(node_id: int, n: int, text: str, user) -> tuple[StageNode, SectionEdit | None, list[StageNode]]:
    """Save one section as a new output version and return the nodes that became stale."""
    if text and not text.endswith("\n"):
        text += "\n"
    with transaction.atomic():
        node = StageNode.objects.select_for_update(of=("self",)).select_related("course").get(pk=node_id)
        reason = edit_block_reason(node)
        if reason:
            raise ValidationError({"text": reason})
        key, document = read_document(node.output_prefix)
        section = document.section(n)
        if section is None:
            raise NotFound("This section does not exist.")
        if section.text == text:
            return node, None, []

        section.text = text
        edit = SectionEdit.objects.create(
            node=node, generated_prefix=node.generated_prefix, n=n, text=text, edited_by=user
        )
        source = node.output_prefix.rstrip("/")
        destination = f"courses/{node.course_id}/nodes/{node.pk}/edits/{edit.pk}"
        _copy_prefix(source, destination, key, document.render().encode())

        node.output_prefix = destination
        node.edited_by = user
        node.edited_at = timezone.now()
        node.save(update_fields=["output_prefix", "edited_by", "edited_at", "updated_at"])

        fresh = set(node.course.stage_nodes.filter(status=StageNode.Status.SUCCEEDED).values_list("pk", flat=True))
        sync_course_staleness(node.course)
        stale = list(
            node.course.stage_nodes.filter(pk__in=fresh, status=StageNode.Status.STALE).select_related("lecture")
        )
    return node, edit, stale
