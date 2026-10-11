# LectureCast

A hosted, multi-user web app that turns course websites and course materials into narrated
slideshows. The plan overview, decisions and milestones are in [PLAN.md](PLAN.md): read it first.
The design is split by topic into `docs/plan/`. Read only the docs the current milestone lists in
PLAN.md, not all of them. When a change cuts across topics, update every doc it touches.

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

## Workflow

- Work is tracked as GitHub issues in milestones M1–M8, one issue per branch, following
  [docs/plan/workstreams.md](docs/plan/workstreams.md). Phase 0 issues live in the library repos.
- One branch per issue, named as the issue says, in its own worktree when sessions run in
  parallel. Check the issue's "Needs first" list is merged before starting.
- `main` is protected: open a PR that closes its issue (`Closes #N`) and passes CI. Addison
  reviews and squash-merges; never merge or enable auto-merge yourself.
- Plan changes go through PRs too, and update every doc they touch.
