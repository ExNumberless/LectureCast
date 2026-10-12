# LectureCast

LectureCast is a hosted, multi-user web app that turns course websites and course materials into
narrated slideshows. Point it at a course website, an MIT OpenCourseWare export or an upload, pick
the lectures you want, and it runs a pipeline that extracts the materials, writes lecture
transcripts with Claude, narrates them with Speechify, and assembles slides you can click through
while listening.

It is built on two libraries:

- [CourseSiteToLectures](https://github.com/ExNumberless/CourseSiteToLectures): providers for
  websites, the Wayback Machine, OCW exports and folders, plus materials extraction and vision
  transcription.
- [SlidesToLectures](https://github.com/ExNumberless/SlidesToLectures): Claude lecture transcripts
  and Speechify narration with MP3 chapters.

LectureCast is in early development. See [PLAN.md](PLAN.md) for the design, decisions, milestones
and current status.

## How it works

- **Courses** are private to their owner. A course comes from a vetted provider (a course
  website, an OCW export or uploaded files); no user code runs on the servers.
- **The pipeline** is a graph of stages with a branch per lecture. Users see every stage and run
  the ones their plan allows, for the lectures they choose, so a course can be partly generated.
- **Editing:** users can edit materials and transcripts before later stages run. The original is
  kept and every edit is shown as a diff.
- **The catalog:** owners can publish a course at any stage. Other users can pick it up and extend
  it with more lectures or later stages, or fork it to use different settings.
- **Plans** (Viewer, Scraper, Audio and Slideshow) come with credits that cover the Claude and
  Speechify costs.

## Stack

- **Backend:** Django, Django REST Framework and Celery, with Postgres and Redis
  ([backend/](backend/)).
- **Frontend:** React, Vite and TypeScript, using pnpm ([frontend/](frontend/)).
- **Infrastructure:** Terraform on AWS (ECS Fargate).
- **Tooling:** [mise](https://mise.jdx.dev/) for tools and tasks, and
  [uv](https://docs.astral.sh/uv/) for Python.

## Local development

You need [mise](https://mise.jdx.dev/) and Docker. mise installs Python, Node, uv, pnpm and
Terraform at the versions in [mise.toml](mise.toml).

```bash
mise install
```

```bash
cp .env.example .env
```

```bash
mise run dev:install
```

```bash
mise run dev
```

`mise run dev` starts the whole stack with docker-compose:

| Service | URL |
|---|---|
| App (Vite, proxying `/api` to Django) | http://localhost:5173 |
| Django API | http://localhost:8000 |
| Mailpit (sign-in emails) | http://localhost:8025 |
| RustFS console (S3-compatible storage) | http://localhost:9001/rustfs/console/ |

Sign in with an email code: the code arrives in Mailpit. Google sign-in works too if you set
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.

### Tasks

| Task | What it does |
|---|---|
| `mise run test` | Run the backend and frontend tests |
| `mise run lint` | Check formatting, lint and types |
| `mise run format` | Format and fix lint |
| `mise run dev:migrate` | Apply database migrations |
| `mise run api-types` | Regenerate the OpenAPI schema and the frontend's TypeScript types |
| `mise run dev:rebuild-frontend` | Recreate the frontend container and reinstall its dependencies |

`mise tasks` lists them all.

## Repository layout

| Path | Contents |
|---|---|
| [backend/](backend/) | Django project (`lecturecast`) and apps: `accounts`, `courses`, `pipeline`, `catalog`, `billing` |
| [frontend/](frontend/) | React single-page app, the generated OpenAPI types and the player schemas |
| [docker/](docker/) | Dockerfiles |
| [docs/plan/](docs/plan/) | The design, split by topic |
| [PLAN.md](PLAN.md) | Plan overview, decisions and milestones |

## Contributing

Work is tracked as GitHub issues in milestones, one branch and one pull request per issue, in the
order set out in [docs/plan/workstreams.md](docs/plan/workstreams.md). `main` is protected: pull
requests need passing CI and a review. Outside contributors should work in a fork.

## License

[MIT](LICENSE)
