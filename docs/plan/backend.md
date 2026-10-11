# Backend (Django + DRF + Celery)

Part of the [LectureCast plan](../../PLAN.md). A Django project, `lecturecast`, in `backend/` (uv,
Python 3.13), with the apps `accounts`, `billing`, `courses`, `pipeline` and `catalog`. The
`pipeline`, `catalog` and `billing` apps are described in their own docs:
[pipeline.md](pipeline.md), [catalog.md](catalog.md) and
[billing-and-costs.md](billing-and-costs.md).

## Accounts and auth

`accounts.User` is a custom user model, created first. Auth uses **django-allauth in headless
mode** with email and Google sign-in, session cookies, and CSRF. Viewers can browse as soon as
they sign up; verifying their email is required before subscribing. The SPA and API share one
domain through CloudFront path routing, which avoids CORS.

## Courses

- `Course(owner, title, source_url | upload, provider, plugin, settings JSON, license,
  visibility [private | published], parent, forked_at_stage)`. A fork has a `parent` and inherits
  the parent's stage outputs before `forked_at_stage` by reference, without copying.
- `Lecture(course, number, name, title, date, audio, duration)`. The lecture list is set by the
  `review` stage, which can drop, rename and renumber lectures.
- `Slide(lecture, n, kind, title, image | markdown, narration, start_ms, end_ms, source,
  locator)`, loaded from `player.json`.

## Provider registry

A settings-level allow-list of CSTL providers and plugins: `website`, `ocw` (zip upload),
`folder` (zip upload), and later Berkeley and AI-agent providers. Only vetted providers and
plugins run; no user code runs on the servers. Each has a JSON schema for its user-editable
settings, such as `site_columns`, `course`, `audience` and `tts_voice`, which the UI renders as a
form. Unknown keys are rejected.

## API (DRF)

`/api/auth/*` (allauth headless), `/api/providers`, `/api/courses`, and
`/api/lectures/{id}/slides`. The pipeline, catalog and billing endpoints are listed in their own
docs.

Media is served through CloudFront signed URLs: short-lived for private courses, cacheable for
published ones.

## Verification

pytest-django for the models and APIs, and provider settings validation (unknown keys rejected,
schemas enforced).
