# Catalog: publishing, picking up and forks

Part of the [LectureCast plan](../../PLAN.md). Covers the shared catalog, how users build on each
other's courses, and moderation. Lives in the backend's `catalog/` app.

Courses are private to their owner until published. Picking up a catalog course extends the one
shared course; a user who wants different stage settings forks it. Published stage outputs are
frozen, and only admins unpublish or take down.

## Models

- `Publication(course, status [pending | approved | rejected], license, attribution,
  reviewed_by)`. Contributors to each stage are credited from `StageNode.run_by`.
- `TakedownRequest` for rights-holder complaints.
- Forks use `Course.parent` and `Course.forked_at_stage` (see [backend.md](backend.md)).

## Publishing

The owner requests publication at any stage after review, and the license is recorded. An admin approves the request. Approval freezes the published nodes, and from
then on only admins can unpublish (including through the takedown flow).

## Picking up

- A user whose plan covers a missing node runs it on the shared catalog course, paying for it in
  credits. This can be a later stage for lectures already started, or lectures nobody has
  generated yet (another Scraper can add materials for lectures 6–10).
- New outputs are added to the catalog course once they pass the same moderation, and each stage
  credits its contributor.
- **Claims.** Starting a run on a shared course claims its target nodes, so two users never pay
  for the same work. A claim expires if the run stalls or fails without a retry.

## Forks

A user who wants different settings for a stage (another `tts_voice` or `audience`), or wants to
change a frozen stage, forks the course at that stage. The fork reuses the earlier outputs by
reference, runs privately, and can be published as a variant of the course. Variants are listed
under the original in the catalog.

## API

`/api/catalog` and `/api/courses/{id}/fork`, plus publication requests and the admin moderation
endpoints.

## Verification

- Approval freezes nodes, and only admins can unpublish.
- Claims block a second run on the same nodes and expire.
- A fork inherits upstream outputs and runs only its own stages.
- Playwright: a multi-user pickup, where a Scraper publishes after materials for lectures 1–2, a
  second Scraper adds lecture 3 from the catalog, and a Slideshow user finishes lecture 1 only,
  charged for that lecture alone.
