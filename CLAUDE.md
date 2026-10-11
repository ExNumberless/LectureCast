# LectureCast

A hosted, multi-user web app that turns course websites and course materials into narrated
slideshows. The full plan, decisions and milestones are in [PLAN.md](PLAN.md): read it first.

## Related repos (local checkouts)

- `~/Projects/CourseSiteToLectures`: the `coursesitetolectures` package (providers for websites,
  the Wayback Machine, OCW exports and folders; materials extraction; vision transcription).
  github.com/ExNumberless/CourseSiteToLectures (not pushed yet).
- `~/Projects/SlidesToLectures`: the `slidestolectures` package (Claude lecture transcripts,
  Speechify TTS with MP3 chapters). github.com/ExNumberless/SlidesToLectures.

Phase 0 of the plan changes those two libraries before any LectureCast code is written.

## Conventions

- mise for tools and tasks, and uv for Python, following the two library repos.
- Backend: Django + DRF + Celery. Frontend: React + Vite + TypeScript (pnpm). Infrastructure:
  Terraform on AWS (ECS Fargate).
- Claude models default to `claude-opus-5-5`. API keys come from `.env` (gitignored), loaded by
  mise.
