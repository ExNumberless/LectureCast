# LectureCast: hosted course-to-narrated-slideshow service

## Context

CourseSiteToLectures (CSTL) and SlidesToLectures (STL) turn course materials into narrated audio.
They were proven on MIT 18.014 (scanned notes) and Berkeley CS 61A Summer 2019 (an archived site
with deleted Google Slides decks). Both run from a CLI, on files, with the user's own API keys.

**LectureCast** is a hosted, multi-user web app built on them:
- A user points a vetted provider at a course website, OCW export or upload, and runs the pipeline.
- The result is a **narrated slideshow**: click through slides and hear each one's narration.
- Courses are private to their owner, who can **publish** one to a shared catalog after a
  license check and moderation.
- Subscriptions with credits cover the Claude and Speechify costs.

Decisions made:
- A new repo, `ExNumberless/LectureCast`.
- Django + DRF + Celery for the backend, and a React (Vite, TypeScript) single-page app.
- Only vetted providers and plugins, configured by settings. No user code runs on the servers.
- AWS ECS Fargate, managed with Terraform. Terraform and CDK do the same job; Terraform gives a
  plain plan/apply review and state stored in S3.

## User levels

The levels are cumulative: each includes everything in the levels above it. Each level is a
`Plan` row, editable in admin, with a set of capabilities, monthly credits and quotas, and a
Stripe price. Tiers can be re-priced or re-scoped without code changes.

| Level | Capabilities | Billing |
|---|---|---|
| **Viewer** (free) | `view_catalog`: browse and play published courses | Free sign-up |
| **Scraper** | + `scrape`: create courses, fetch or upload, run `materials` (including vision), review and edit materials | Subscription with credits |
| **Audio** | + `transcribe` and `narrate`: lecture transcripts (Claude) and narrated MP3s (Speechify), download audio | Higher tier |
| **Slideshow** | + `slideshow` and `publish`: generate narrated slideshows (the `slides` step and the player for their own courses), request catalog publication | Top tier |
| **Admin** (you) | `is_staff`/superuser: Django admin, the cost dashboard, moderation, plan editing | Not sold |

The plan assumes lecture transcripts belong to the Audio level, because they are what Audio
narrates and their cost is mostly Claude output. Scraper is fetch plus materials. This can be
moved between levels in admin.

DRF checks capabilities with a `HasCapability("narrate")` permission class. The UI hides or
disables steps the user's plan doesn't include and shows an upgrade prompt instead.

## Cost monitoring (admin)

- **Usage events.** `UsageEvent(user, plan, course, job, step, vendor [anthropic | speechify],
  model or voice, input_tokens, output_tokens, cache_read_tokens, characters, requests, cost_usd,
  at)` is written by the `JobReporter` from the libraries' usage callbacks (Phase 0) for every
  Claude call and Speechify request.
- **Prices.** `cost_usd` is computed from a `PriceTable(vendor, sku, unit, price, effective_from)`
  edited in admin, so historical costs stay correct when prices change.
- **Infrastructure costs.** A daily Celery beat task pulls AWS spend by service from the Cost
  Explorer API into `InfraCost` rows. Revenue comes from dj-stripe's synced invoices.
- **Reconciliation.** Optionally, a daily check compares the recorded totals with Anthropic's
  Usage & Cost Admin API (it needs an admin API key) and Speechify's usage, to catch untracked
  spend.
- **Admin dashboard,** a staff-only page in the React app backed by `/api/admin/costs/*`:
  - spend by day, vendor, step, model, user and plan;
  - average cost per lecture, per slideshow and per course;
  - revenue against cost per plan, giving margin per tier;
  - top users, with CSV export.
- **What-if tool.** Adjust credit prices, quotas and plan prices, and see projected margin for
  each tier against the last 30 or 90 days of real usage.
- **Alerts.** Email when daily spend passes a threshold or a user's usage spikes. Hard monthly
  caps per plan are enforced before a job starts, using the cost estimate.

## Phase 0: library work in CSTL and STL (prerequisite)

The web worker calls the libraries as Python APIs, not through the CLI.

1. **Progress and usage reporting.** Add an optional `reporter` (a small protocol with `step()`,
   `log()` and `usage()`) to:
   - STL: `lecture.run` and `tts.run`, replacing `print`/`Progress` in
     `slidestolectures/tts.py` and `lecture.py`.
   - CSTL: `materials.run`, `vision.run` and `WebsiteProvider.fetch`, replacing the roughly 16
     `print` calls.
   The default reporter prints, so the CLI doesn't change. Usage records Claude input and output
   tokens per call and Speechify characters, which billing needs.
2. **Chapter times.** STL `tts.encode` already computes `chapters`. Also write
   `<audio dir>/<name>.chapters.json` (`[{n, title, start_ms, end_ms}]`) so nothing has to read
   them back from the MP3.
3. **A new CSTL step, `slides`**, in `coursesitetolectures/slides.py` with a CLI command. For
   each lecture it writes `slides/<name>/player.json` and slide images. It joins:
   - each section's source and locator, from `course.json` (`materials.index`);
   - each section's narration, from `## [N]` sections of the lecture transcript (the same split
     as STL `tts.SECTION`);
   - each section's audio start and end, from `chapters.json`.
   Each slide is one of these kinds:
   - `image`: a PDF page or scanned page rendered to WebP with pymupdf. PPTX is converted to PDF
     with LibreOffice when it's installed, else it falls back to markdown.
   - `markdown`: rebuilt Google Slides, HTML, Markdown, notebook cells, and transcribed text.
   - `code`: example code files.
4. **Cost estimates.** `estimate(step, workspace)` gives expected Claude tokens and Speechify
   characters before a run. It should be calibrated from the two test courses, where transcripts
   ran about 4,000 words, or 24,000–27,000 characters, per lecture.
5. **Publish both packages to PyPI.** STL first, then CSTL without its git `[tool.uv.sources]`
   entry. LectureCast pins exact versions.

## LectureCast repository layout

```
LectureCast/
  backend/                  Django project "lecturecast" (uv, Python 3.13)
    accounts/  billing/  courses/  jobs/  catalog/
  frontend/                 Vite + React + TypeScript (pnpm)
  infra/terraform/          modules: network, ecs, rds, redis, storage_cdn, secrets, ses; envs: staging, prod
  docker/                   api.Dockerfile, worker.Dockerfile (ffmpeg, libreoffice-impress, fonts)
  docker-compose.yml        postgres, redis, minio (S3), api, worker, vite dev server
  mise.toml                 python, node, uv, pnpm, terraform, and tasks: dev, test, lint, migrate, tf-plan
  .github/workflows/        ci.yml (tests, lint, type-check, terraform validate), deploy.yml
```

## Backend (Django + DRF + Celery)

**Models**
- `accounts.User`: a custom user model, created first. Auth uses **django-allauth in headless
  mode** with email and Google sign-in, session cookies, and CSRF. The SPA and API share one
  domain through CloudFront path routing, which avoids CORS.
- `billing`:
  - Stripe subscriptions through **dj-stripe**, with plans that grant monthly credits.
  - `CreditLedger(user, delta, reason, job)` records every grant and charge.
  - Credits are priced from metered usage, at a fixed price per thousand tokens and per thousand
    characters, set in admin.
- `courses`:
  - `Course(owner, title, source_url | upload, provider, plugin, settings JSON, license,
    visibility [private | published], workspace S3 prefix)`.
  - `Lecture(course, number, name, title, date, audio, duration)`.
  - `Slide(lecture, n, kind, title, image | markdown, narration, start_ms, end_ms, source,
    locator)`, loaded from `player.json`.
- `jobs`:
  - `Job(course, steps, status, estimate, actual_usage, error)`.
  - `JobStep(job, name, status, progress, log, usage, started, finished)`.
- `catalog`:
  - `Publication(course, status [pending | approved | rejected], license, attribution,
    reviewed_by)`.
  - `TakedownRequest` for rights-holder complaints.

**Provider registry.** A settings-level allow-list of CSTL providers and plugins: `website`,
`ocw` (zip upload), `folder` (zip upload), and later Berkeley and AI-agent providers. Each has a
JSON schema for its user-editable settings, such as `site_columns`, `course`, `audience` and
`tts_voice`, which the UI renders as a form. Unknown keys are rejected.

**Pipeline tasks** (Celery, Redis broker)
- One task per step: fetch, materials (with vision), lecture, tts, slides.
- Each task:
  1. syncs the course workspace from S3 into local scratch storage;
  2. calls the CSTL/STL API with a `JobReporter` that writes progress to `JobStep`;
  3. uploads outputs back to S3, including the `.cache/` folders so re-runs are incremental;
  4. records usage, and charges credits as each step finishes.
- Steps are chained. A failed step can be retried without redoing the steps before it.
- Speechify calls go to a `tts` queue with a fixed worker concurrency, so the total request rate
  stays under the plan's limits across all users.

**Flow:** create course → fetch (website) or upload (OCW / folder) → review the lecture list and
skip lectures → **cost estimate, then confirm** (reserve credits) → materials → lecture → tts →
slides → player.

**Safety checks** in the worker:
- **SSRF:** resolve each URL and reject private, loopback, link-local and metadata addresses,
  enforced in CSTL's `Web` client through an injectable URL validator.
- **Limits:** download size and count caps, and per-job timeouts.
- **Uploads:** zip size, file-count and decompression-ratio checks.
- **Per-user limits:** concurrent jobs and a monthly cap.

**Publishing:** the owner requests publication, attests to having the rights, and the license is
recorded. OCW's metadata gives its license automatically; non-commercial licenses are flagged for
review. An admin approves the request, and a takedown flow can unpublish a course.

**API (DRF):** `/api/auth/*` (allauth headless), `/api/providers`, `/api/courses`,
`/api/courses/{id}/estimate`, `/api/courses/{id}/jobs`, `/api/jobs/{id}` (polled every 2
seconds), `/api/lectures/{id}/slides`, `/api/catalog`, `/api/billing/*`, and a Stripe webhook.
Media is served through CloudFront signed URLs: short-lived for private courses, cacheable for
published ones.

## Frontend (React + Vite + TypeScript)

Built with React Router and TanStack Query, with Tailwind and shadcn/ui for components.

**Pages:** sign-in and sign-up; My courses; New course (choose a provider, then fill its settings
form); course detail (lectures, job progress, estimate-and-confirm); player; catalog; account and
billing (Stripe Checkout and the customer portal).

**Player:**
- One `<audio>` element per lecture MP3. Each slide seeks to its `start_ms`; playback stops or
  auto-advances at `end_ms`.
- Controls: previous/next, keyboard (arrow keys and space), auto-advance toggle, playback speed,
  and a progress bar with slide markers.
- A narration transcript panel highlights the current slide.
- Markdown slides render KaTeX for math (the 18.014 transcriptions are in LaTeX). Code slides use
  syntax highlighting.
- Deep links: `/courses/:id/lectures/:n/slides/:k`.

## AWS (Terraform)

- A VPC with public and private subnets.
- **ECS Fargate services:** `api` (gunicorn behind an ALB), `worker` (Celery, default queue),
  `worker-tts` (the `tts` queue), and `beat`.
- **Data:** RDS Postgres and ElastiCache Redis.
- **S3:** a private media bucket and a SPA bucket, both behind CloudFront. Routes: `/api/*` to
  the ALB, `/media/*` to S3 with signed URLs, everything else to the SPA.
- **Secrets Manager** holds the Anthropic, Speechify, Stripe and Django keys. SES sends email.
  Images are stored in ECR.
- **Terraform state** lives in S3 with DynamoDB locking, with staging and prod environments.
- **CI deploys** through GitHub OIDC: build and push images, run migrations as a one-off task,
  update services, and upload the SPA.

## Handoff to a new chat

On approval:
1. Create `~/Projects/LectureCast` (git init, `main` branch) with this plan as `PLAN.md`, and a
   short `CLAUDE.md` pointing to it and to the CSTL and STL repos.
2. Save memory notes about the decisions.

Implementation then starts in a fresh chat in that folder, beginning with Phase 0 in the
library repos.

## Milestones (each one is shippable)

1. Phase 0 library work, with packages published.
2. Repo scaffold and local docker-compose, with auth working end to end.
3. Courses, jobs and pipeline tasks running locally on MinIO, with no billing yet.
4. The player. Done when CS 61A lecture 1 and 18.014 chapter A play correctly.
5. User levels and billing: plans and capabilities, Stripe test mode, estimates, credits and
   limits, and usage events with the admin cost dashboard.
6. Terraform for staging and deploy to it, then prod.
7. Catalog publishing, moderation and takedown.
8. Later: the AI-agent structure provider (planned earlier), and Save Page Now archiving with the
   archive.org S3-like keys.

## Verification

- **Libraries:** pytest for the reporters, `chapters.json`, `slides`/`player.json` (against a
  fixture course) and estimates. Re-run the two test courses through the CLI and check that
  `player.json` slide times line up with the MP3 chapters.
- **Backend:** pytest-django for the models and APIs, capability checks per level (for example,
  a Scraper can't start `tts`), usage event cost calculation against the price table, Celery tasks with eager mode and fake
  CSTL/STL reporters, provider settings validation, SSRF validator cases, and zip-bomb rejection.
  Stripe webhooks are tested with dj-stripe fixtures in test mode.
- **Frontend:** Vitest for the player logic (seek and auto-advance by chapter times), and
  Playwright end to end: sign up, create a course from a fixture site, run the jobs with stub
  pipeline steps, and play through slides.
- **Infrastructure:** `terraform validate` and `plan` in CI, a staging deploy, and a smoke test
  that runs a real job on one OCW lecture.
