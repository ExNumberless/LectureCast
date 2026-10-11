# Frontend (React + Vite + TypeScript)

Part of the [LectureCast plan](../../PLAN.md). A single-page app in `frontend/` (pnpm), built with
React Router and TanStack Query, with Tailwind and shadcn/ui for components.

## Pages

Sign-in and sign-up; My courses; New course (choose a provider, then fill its settings form);
course detail with the pipeline view; player; catalog; account and billing (Stripe Checkout and
the customer portal); and the staff-only cost dashboard (see
the private billing plan).

## Pipeline view

See [pipeline.md](pipeline.md) for the stages and runs.
- The stage graph is drawn with a row per lecture and the stages as columns, and course-level
  stages at the start.
- Each node shows its status: pending, queued, running (with progress), done, failed, stale,
  claimed or locked. Locked nodes, outside the user's plan, show an upgrade prompt.
- Clicking a node shows its log, usage and contributor, with Run, Retry and Fork buttons.
- Choosing lectures and a target stage opens the estimate-and-confirm dialog for the run.

## Catalog

See [catalog.md](catalog.md). Each course shows a coverage summary (how many lectures have
reached materials, transcripts, audio and slideshow, as a compact lecture × stage grid) and its
variants. Viewers see courses with at least one playable lecture. Paid tiers also get a "ready for
you" filter listing courses with nodes their plan can run, whether later stages or lectures not
started.

## Player

- Lists only the lectures that have reached the player.
- One `<audio>` element per lecture MP3. Each slide seeks to its `start_ms`; playback stops or
  auto-advances at `end_ms`.
- Controls: previous/next, keyboard (arrow keys and space), auto-advance toggle, playback speed,
  and a progress bar with slide markers.
- A narration transcript panel highlights the current slide.
- Markdown slides render KaTeX for math (the 18.014 transcriptions are in LaTeX). Code slides use
  syntax highlighting.
- Deep links: `/courses/:id/lectures/:n/slides/:k`.

## Verification

- Vitest for the player logic (seek and auto-advance by chapter times).
- Playwright end to end: sign up, create a course from a fixture site, run the pipeline with stub
  stages, and play through slides. The multi-user pickup test is in [catalog.md](catalog.md).
