# Billing, capabilities and cost monitoring

Part of the [LectureCast plan](../../PLAN.md). The user levels themselves are in the plan
overview. Lives in the backend's `billing/` app and the admin dashboard.

## Plans and capabilities

- Each level is a `Plan` row, editable in admin, with a set of capabilities, monthly credits and
  quotas, and a Stripe price.
- DRF checks capabilities with a `HasCapability("narrate")` permission class. A pipeline run is
  accepted only if the user's plan covers every stage it would execute (see
  [pipeline.md](pipeline.md)).

## Subscriptions and credits

- Stripe subscriptions through **dj-stripe**, with plans that grant monthly credits. Stripe
  Checkout and the customer portal handle sign-up and changes. Users verify their email before
  subscribing.
- **Stripe Tax** from the start, for sales tax and VAT.
- **Rollover:** unused monthly credits carry over at renewal, up to a cap set per plan (for
  example, one month's grant). Credits above the cap expire.
- **Top-ups:** one-off credit packs bought through Stripe Checkout, which don't expire.
- **Trial grant:** a small one-time grant on a user's first paid subscription, enough for about
  one lecture.
- `CreditLedger(user, delta, reason [grant | rollover | expire | topup | trial | reserve |
  release | charge], run)` records every change. Credits are spent oldest grant first, top-ups
  last.
- Credits are priced from metered usage, at a fixed price per thousand tokens and per thousand
  characters, set in admin.
- A run reserves credits from its estimate when confirmed, and each node is charged as it
  finishes. Each user pays only for the nodes (stage × lecture) they run, including on catalog
  courses they pick up.
- Hard monthly caps per plan are enforced before a run starts, using the cost estimate.

## Cost monitoring (admin)

- **Usage events.** `UsageEvent(user, plan, course, run, stage, lecture,
  vendor [anthropic | speechify], model or voice, input_tokens, output_tokens, cache_read_tokens,
  characters, requests, cost_usd, at)` is written by the `JobReporter` from the libraries' usage
  callbacks (Phase 0) for every Claude call and Speechify request.
- **Prices.** `cost_usd` is computed from a `PriceTable(vendor, sku, unit, price, effective_from)`
  edited in admin, so historical costs stay correct when prices change.
- **Infrastructure costs.** A daily Celery beat task pulls AWS spend by service from the Cost
  Explorer API into `InfraCost` rows. Revenue comes from dj-stripe's synced invoices.
- **Reconciliation.** Optionally, a daily check compares the recorded totals with Anthropic's
  Usage & Cost Admin API (it needs an admin API key) and Speechify's usage, to catch untracked
  spend.
- **Admin dashboard,** a staff-only page in the React app backed by `/api/admin/costs/*`:
  - spend by day, vendor, stage, model, user and plan;
  - average cost per lecture, per slideshow and per course;
  - revenue against cost per plan, giving margin per tier;
  - top users, with CSV export.
- **What-if tool.** Adjust credit prices, quotas and plan prices, and see projected margin for
  each tier against the last 30 or 90 days of real usage.
- **Alerts.** Email when daily spend passes a threshold or a user's usage spikes.

## API

`/api/billing/*`, the Stripe webhook, and `/api/admin/costs/*`.

## Verification

- Capability checks per level (for example, a Scraper can't start `tts`).
- Usage event cost calculation against the price table, including a price change.
- Credit reservation and per-node charging for a partial run.
- Rollover up to the cap, expiry above it, top-ups that never expire, and the trial grant given
  once.
- Stripe webhooks with dj-stripe fixtures in test mode.
