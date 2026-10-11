# Pipeline

Part of the [LectureCast plan](../../PLAN.md). Covers the stage graph, runs, scheduling, the
Celery workers and their safety checks. Lives in the backend's `pipeline/` app.

## Stages

Stages are defined in code, in a registry in `pipeline/`. Each has a name, a scope (course or
lecture), its upstream stages, the capability it needs (see
the private billing plan), its Celery queue and the CSTL/STL function it
calls (see [phase0-libraries.md](phase0-libraries.md)):

| Stage | Scope | Depends on | Capability |
|---|---|---|---|
| `fetch` (or `upload`) | course | | `scrape` |
| `review` (confirm the lecture list; a gate, not a task) | course | fetch | `scrape` |
| `materials` (including vision) | lecture | review | `scrape` |
| `transcript` | lecture | materials | `transcribe` |
| `tts` | lecture | transcript | `narrate` |
| `render` (slide images) | lecture | materials | `slideshow` |
| `assemble` (`player.json`) | lecture | tts, render | `slideshow` |

```
                        ┌─ lecture 1: materials ─┬─ transcript ─ tts ─┐
fetch / upload ─ review ┤                        └──── render ────────┴─ assemble
                        └─ lecture N: …   (branches run in parallel)
```

## Models

- `StageNode(course, stage, lecture?, status, settings_hash, inputs_hash, output S3 prefix,
  run_by, frozen, claimed_by, claim_expires)`: one node of a course's graph, holding the current
  output of one stage for one lecture (or for the course).
- `PipelineRun(course, requested_by, targets, status, estimate, actual_usage, error)`.
- `StageRun(run, node, status, progress, log, usage, started, finished)`: one execution of a node
  within a run.

## Runs

- **Review.** Review confirms which entries in the fetched sequence are real lectures (dropping
  non-lectures and duplicates) and fixes titles and numbering. It defines the course's lecture
  list. It doesn't decide what gets generated.
- **Lecture selection.** Each run targets a set of lectures from that list (a range, a pick list,
  or all) and a stage, or everything up to a stage. The estimate covers only the selected
  lectures, so a user can spend part of their credits now and generate more later. Lectures not
  selected stay at whatever stage they reached.
- **Planning a run.** From the targets, the server adds every upstream node that is missing or
  stale and checks that the user's plan covers all of them. On a shared catalog course it also
  claims the nodes (see [catalog.md](catalog.md)). Then it shows the **cost estimate for the
  whole run** and, once the user confirms, reserves the credits.
- **Scheduling from the database.** The pipeline is scheduled from the database, not with Celery
  chains. When a node finishes, its task marks it done and queues every node whose upstream
  nodes are all done. A failed node can be retried alone, part of a graph can be run, and work
  resumes after a worker restart.
- **Staleness.** Each node records a hash of its inputs and settings. Editing materials or
  re-running an upstream node marks the nodes after it stale; they aren't re-run automatically.
  Frozen (published) nodes never go stale: changing them happens in a fork (see
  [catalog.md](catalog.md)).

**Flow:** create course → fetch (website) or upload (OCW / folder) → review the lecture list →
choose lectures and a target stage → **cost estimate, then confirm** → the graph runs → player
(for the lectures that have reached it). Repeat for more lectures or later stages. The course can
be published at any point after review.

## Tasks and workers

Celery with a Redis broker. Each task:
1. builds a local workspace from the S3 outputs of the node's upstream nodes, including inherited
   ones for a fork;
2. calls the CSTL/STL API with a `JobReporter` that writes progress to `StageRun` and usage to
   `UsageEvent`;
3. uploads outputs to the node's S3 prefix, including the `.cache/` folders so re-runs are
   incremental;
4. charges credits as each node finishes.

**Concurrency.** Lecture branches run in parallel, up to a per-user limit on running nodes.
Speechify calls go to a `tts` queue with a fixed worker concurrency, so the total request rate
stays under the plan's limits across all users.

## Safety checks

In the worker:
- **SSRF:** resolve each URL and reject private, loopback, link-local and metadata addresses,
  enforced in CSTL's `Web` client through an injectable URL validator.
- **Limits:** download size and count caps, and per-node timeouts.
- **Uploads:** zip size, file-count and decompression-ratio checks.
- **Per-user limits:** running nodes and a monthly cap.

## API

`/api/pipeline` (the stage graph, with the user's lock state per stage),
`/api/courses/{id}/graph` (nodes and their status), `/api/courses/{id}/estimate`,
`/api/courses/{id}/runs`, and `/api/runs/{id}` (polled every 2 seconds).

## Verification

- The scheduler queues exactly the ready nodes, runs lecture branches in parallel, retries one
  failed node without re-running the others, generates and estimates only the selected lectures,
  and resumes after a simulated worker restart.
- Staleness propagates on upstream changes but not to frozen nodes.
- A run that includes a stage outside the user's plan is rejected, whether that stage is a
  target or an upstream node.
- Celery tasks run in eager mode with fake CSTL/STL reporters.
- SSRF validator cases and zip-bomb rejection.
