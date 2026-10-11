# LectureCast: hosted course-to-narrated-slideshow service

This is the plan overview. The design is split by topic into [docs/plan/](docs/plan/); each
milestone below lists the docs it needs.

| Doc | Covers |
|---|---|
| [phase0-libraries.md](docs/plan/phase0-libraries.md) | Changes to CSTL and STL before LectureCast |
| [pipeline.md](docs/plan/pipeline.md) | Stage graph, runs, lecture selection, scheduling, workers, safety checks |
| [catalog.md](docs/plan/catalog.md) | Publishing, picking up, claims, forks and variants, moderation |
| [billing-and-costs.md](docs/plan/billing-and-costs.md) | Plans and capabilities, credits, Stripe, usage events, cost dashboard |
| [backend.md](docs/plan/backend.md) | Django apps, auth, courses, provider registry, core API |
| [frontend.md](docs/plan/frontend.md) | Pages, pipeline view, catalog UI, player |
| [infra.md](docs/plan/infra.md) | Repo layout, docker-compose, Terraform, CI and deploy |

## Context

CourseSiteToLectures (CSTL) and SlidesToLectures (STL) turn course materials into narrated audio.
They were proven on MIT 18.014 (scanned notes) and Berkeley CS 61A Summer 2019 (an archived site
with deleted Google Slides decks). Both run from a CLI, on files, with the user's own API keys.

**LectureCast** is a hosted, multi-user web app built on them:
- A user points a vetted provider at a course website, OCW export or upload, and runs the
  pipeline.
- Generation is a **pipeline of stages** (a DAG with a branch per lecture). Users see the stages
  and trigger the ones their subscription tier allows, for the lectures they choose.
- The result is a **narrated slideshow**: click through slides and hear each one's narration.
- Courses are private to their owner, who can **publish** one to a shared catalog at any stage
  after a license check and moderation. Other users can **pick up** a catalog course and extend
  it with more lectures or later stages, so a Scraper's materials can become someone else's
  narrated slideshow.
- Subscriptions with credits cover the Claude and Speechify costs.

## Decisions

- A new repo, `ExNumberless/LectureCast`.
- Django + DRF + Celery for the backend, and a React (Vite, TypeScript) single-page app.
- Only vetted providers and plugins, configured by settings. No user code runs on the servers.
- The pipeline is scheduled from the database (a stage graph), not with Celery chains.
- Users choose which lectures to generate, so a run can spend only part of their credits. A
  course can be partly generated: some lectures further along than others.
- Picking up a catalog course extends the one shared course, with more lectures, later stages or
  both. A user who wants different stage settings (another voice or audience) forks it from that
  stage. Published stage outputs are frozen, and only admins unpublish or take down.
- AWS ECS Fargate, managed with Terraform.

## User levels

The levels are cumulative: each includes everything in the levels above it. Each level is a
`Plan` row, editable in admin, so tiers can be re-priced or re-scoped without code changes (see
[billing-and-costs.md](docs/plan/billing-and-costs.md)).

| Level | Capabilities | Billing |
|---|---|---|
| **Viewer** (free) | `view_catalog`: browse and play published courses | Free sign-up |
| **Scraper** | + `scrape` and `publish`: create courses, fetch or upload, run `materials` (including vision), review and edit materials, request catalog publication | Subscription with credits |
| **Audio** | + `transcribe` and `narrate`: lecture transcripts (Claude) and narrated MP3s (Speechify), download audio | Higher tier |
| **Slideshow** | + `slideshow`: generate narrated slideshows (the `render` and `assemble` stages, and the player for their own courses) | Top tier |
| **Admin** (you) | `is_staff`/superuser: Django admin, the cost dashboard, moderation, plan editing | Not sold |

The plan assumes lecture transcripts belong to the Audio level, because they are what Audio
narrates and their cost is mostly Claude output. Scraper is fetch plus materials. This can be
moved between levels in admin.

Each pipeline stage names the capability it needs, and a run is accepted only if the user's plan
covers every stage it would execute. The pipeline view shows stages outside the user's plan as
locked, with an upgrade prompt.

Tiers work together through the catalog: a Scraper can take a course through materials and
publish it, an Audio user can pick it up and add transcripts and narration, and a Slideshow user
can finish it. Users also extend a course sideways: one user narrates lectures 1–5, and another
later narrates 6–10. Each user pays only for the nodes (stage × lecture) they run.

## Milestones (each one is shippable)

| # | Milestone | Docs |
|---|---|---|
| 1 | Phase 0 library work, with packages published. | phase0-libraries |
| 2 | Repo scaffold and local docker-compose, with auth working end to end. | infra, backend, frontend |
| 3 | Courses and the pipeline (stage registry, graph scheduler, runs and the pipeline view) running locally on MinIO, with no billing yet. | backend, pipeline, frontend |
| 4 | The player. Done when CS 61A lecture 1 and 18.014 chapter A play correctly. | frontend, backend |
| 5 | User levels and billing: plans and capabilities, Stripe test mode, estimates, credits and limits, and usage events with the admin cost dashboard. | billing-and-costs, pipeline |
| 6 | Terraform for staging and deploy to it, then prod. | infra |
| 7 | Catalog publishing at any stage, moderation, picking up (claims and contributor credit), forks and variants, and takedown. | catalog, pipeline, frontend |
| 8 | Later: the AI-agent structure provider (planned earlier), and Save Page Now archiving with the archive.org S3-like keys. | backend, pipeline |

Each topic doc ends with its own verification section.
