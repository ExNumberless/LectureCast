# Infrastructure: repo, local dev, AWS and CI

Part of the [LectureCast plan](../../PLAN.md).

## Repository layout

```
LectureCast/
  backend/                  Django project "lecturecast" (uv, Python 3.13)
    accounts/  billing/  courses/  pipeline/  catalog/
  frontend/                 Vite + React + TypeScript (pnpm)
  infra/terraform/          modules: network, ecs, rds, redis, storage_cdn, secrets, ses; envs: staging, prod
  docker/                   api.Dockerfile, worker.Dockerfile (ffmpeg, libreoffice-impress, fonts)
  docker-compose.yml        postgres, redis, rustfs (S3), mailpit, api, worker, vite dev server
  mise.toml                 python, node, uv, pnpm, terraform, and tasks: dev, test, lint, migrate, tf-plan
  .github/workflows/        ci.yml (tests, lint, type-check, terraform validate), deploy.yml
  docs/plan/                the plan's topic docs
```

## AWS (Terraform)

AWS ECS Fargate, managed with Terraform. Terraform and CDK do the same job; Terraform gives a
plain plan/apply review and state stored in S3.

Staging goes up in M3 and prod in M6. The domain and AWS account aren't chosen yet, so they are
Terraform variables. Sizing keeps idle costs low, aiming at roughly $60–100 a month for prod and
close to nothing for idle staging:
- staging's services scale to zero, and its database stops, when it isn't in use;
- workers run on Fargate Spot (a stage interrupted mid-run is retried by the scheduler);
- one NAT gateway, or VPC endpoints for S3, ECR and Secrets Manager in its place;
- the smallest RDS and ElastiCache instances, sized up from real usage.

- A VPC with public and private subnets.
- **ECS Fargate services:** `api` (gunicorn behind an ALB), `worker` (Celery, default queue),
  `worker-tts` (the `tts` queue), and `beat`.
- **Data:** RDS Postgres and ElastiCache Redis.
- **S3:** a private media bucket and a SPA bucket, both behind CloudFront. Routes: `/api/*` to the
  ALB, `/media/*` to S3 with signed URLs, everything else to the SPA.
- **Secrets Manager** holds the Anthropic, Speechify, Stripe and Django keys. SES sends email.
  Images are stored in ECR.
- **Terraform state** lives in S3 with DynamoDB locking, with staging and prod environments.
- **CI deploys** through GitHub OIDC: build and push images, run migrations as a one-off task,
  update services, and upload the SPA.

## Verification

`terraform validate` and `plan` in CI, a staging deploy, and a smoke test that runs a real
pipeline on one OCW lecture.
