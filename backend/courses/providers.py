from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    description: str
    source_kind: str
    settings_schema: dict


PROVIDER_REGISTRY = {
    "website": ProviderDefinition(
        id="website",
        name="Course website",
        description="Fetch course materials from a public website.",
        source_kind="url",
        settings_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "site_columns": {
                    "type": "array",
                    "title": "Schedule columns to include",
                    "description": (
                        "Optional. By default, LectureCast uses links in the schedule's Lecture column. "
                        "Add other schedule columns that contain materials you want included. "
                        "Separate names with commas; use | for alternatives, like textbook|reading."
                    ),
                    "items": {"type": "string"},
                },
                "course": {
                    "type": "string",
                    "title": "Course subject",
                    "description": (
                        "Optional context for the generated lectures. For example: Calculus with theory. "
                        "This is separate from the course name in your library."
                    ),
                },
                "audience": {
                    "type": "string",
                    "title": "Who are the lectures for?",
                    "description": (
                        "Optional. Describe the learners' background or level, for example: "
                        "undergraduates who know some Python."
                    ),
                },
            },
            "additionalProperties": False,
        },
    ),
    "ocw": ProviderDefinition(
        id="ocw",
        name="MIT OpenCourseWare",
        description="Upload an MIT OpenCourseWare export ZIP archive.",
        source_kind="upload",
        settings_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "course": {
                    "type": "string",
                    "title": "Course subject",
                    "description": (
                        "Optional context for the generated lectures. For example: Calculus with theory. "
                        "This is separate from the course name in your library."
                    ),
                },
                "audience": {
                    "type": "string",
                    "title": "Who are the lectures for?",
                    "description": (
                        "Optional. Describe the learners' background or level, for example: "
                        "undergraduates who know some Python."
                    ),
                },
            },
            "additionalProperties": False,
        },
    ),
    "folder": ProviderDefinition(
        id="folder",
        name="Upload materials",
        description="Upload a ZIP archive containing course materials.",
        source_kind="upload",
        settings_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
        },
    ),
}


def enabled_providers():
    allowlist = getattr(settings, "COURSE_PROVIDER_ALLOWLIST", list(PROVIDER_REGISTRY))
    unknown = set(allowlist) - set(PROVIDER_REGISTRY)
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown course providers in COURSE_PROVIDER_ALLOWLIST: {', '.join(sorted(unknown))}"
        )
    return [PROVIDER_REGISTRY[key] for key in allowlist]


def get_provider(provider_id):
    for provider in enabled_providers():
        if provider.id == provider_id:
            return provider
    return None


def validate_provider_settings(provider, values):
    errors = sorted(
        Draft202012Validator(provider.settings_schema).iter_errors(values), key=lambda error: list(error.path)
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path)
        field = f"{location}: " if location else ""
        raise ValueError(f"Invalid provider settings: {field}{error.message}")
