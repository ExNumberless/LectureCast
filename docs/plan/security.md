# Security

Part of the [LectureCast plan](../../PLAN.md). Covers AWS accounts and access, the network, data
protection, worker isolation, detection, edge protection and the security checks in CI. The
infrastructure it applies to is in [infra.md](infra.md); the SSRF, download and zip checks in the
workers are in [pipeline.md](pipeline.md#safety-checks).

The controls follow the AWS recipes in *Cloud Native Security Cookbook* (Josh Armitage, O'Reilly,
2022), scaled down for an app run by one person on a small budget. The recipes built for large
organizations are listed under [Not adopted](#not-adopted), with the reason.

## Principles

- **Least privilege.** Each person, CI job and ECS service gets only the permissions and secrets
  it needs.
- **Defense in depth.** A failure in one layer is caught by the next: the SSRF check in code is
  backed by an isolated worker with almost no permissions, and security groups are backed by
  network ACLs and route tables.
- **Change only through CI.** People have read-only access day to day. Infrastructure and deploys
  change through reviewed PRs and the CI roles.
- **Almost no secrets in Terraform.** Terraform creates secrets but never sees their values, with
  two exceptions: the ElastiCache AUTH token and the CloudFront origin header, which AWS takes as
  resource arguments, so they land in state. Both are generated with `random_password`, readable
  only by the CI roles and the admin permission set, and rotated by a Terraform change (see
  [Data](#data)).

## Accounts and access

An AWS Organization with three accounts:

| Account | Holds |
|---|---|
| management | The organization, its policies, IAM Identity Center, the CloudTrail log bucket and the backup vault. No workloads. |
| staging | The staging environment. |
| prod | The prod environment. |

- **Service control policies** on the staging and prod accounts deny:
  - every region except the chosen one, exempting the global services AWS lists (CloudFront's
    ACM certificate, IAM, WAF for CloudFront and others in us-east-1);
  - stopping or deleting CloudTrail, disabling GuardDuty, leaving the organization, and
    deleting the CloudTrail log bucket or its objects;
  - any action by the account's root user. The few tasks that need root (some account settings,
    closing an account) are done by detaching that policy from the management account for the
    task and attaching it again afterwards.
- **People** sign in through IAM Identity Center with MFA. The default permission set is
  read-only. An admin permission set is used for bootstrapping and incidents only. There are no
  IAM users, and root users have MFA and no access keys.
- **CI** reaches AWS through GitHub OIDC, with two roles in each workload account:
  - `ci-plan`: read-only plus the Terraform state, trusted for pull requests from
    `ExNumberless/LectureCast`. Runs `terraform plan`. Its trust policy matches the
    `pull_request` event from this repository only. The repo is public, but fork PRs don't get
    `id-token: write`, so they can't assume it, and no workflow uses `pull_request_target` with a
    checkout of PR code.
  - `ci-deploy`: applies Terraform, pushes images, runs migrations and updates services. Trusted
    only for the GitHub environment of the same name (`staging` or `prod`), and those environments
    accept deploys from `main` only.
- **Terraform state** sits in a bucket in each account, with versioning, encryption and public
  access blocked. Only the CI roles and the admin permission set can read it, and CloudTrail
  logs S3 data events on the bucket, so every read of state is recorded with who made it. The `org`
  environment (accounts, policies, Identity Center, CloudTrail) is applied by hand with the
  admin permission set, since it changes rarely and CI has no access to the management account.

## Network

The VPC has three subnet tiers in two availability zones:

| Tier | Holds | Routes |
|---|---|---|
| public | ALB, NAT gateway | internet gateway |
| private | ECS tasks | NAT gateway, S3 and DynamoDB gateway endpoints |
| internal | RDS, ElastiCache | none outside the VPC |

- Security groups allow traffic from other security groups, never from address ranges: RDS and
  Redis accept connections only from the ECS services' groups, and `api` only from the ALB.
- Network ACLs back the security groups: the internal subnets accept traffic only from the
  private subnets.
- The ALB accepts only CloudFront: its security group allows the CloudFront origin-facing
  prefix list, and its listener rejects requests without a secret origin header that CloudFront
  adds. The header value is a `random_password`, so it is in Terraform state; to rotate it, the
  listener rule accepts the old and new values until CloudFront has deployed the new one. The
  header is a weak control on its own: anyone with the value could still only reach the ALB
  through a CloudFront distribution, and would skip WAF and caching, not authentication.
- One NAT gateway carries traffic to the internet (course sites, Anthropic, Speechify, and AWS
  APIs). S3 and DynamoDB use the free gateway endpoints. Interface endpoints (ECR, Secrets
  Manager, KMS, Logs) would cost about $7 a month each per availability zone, $40–60 in all, so
  that traffic goes through the NAT, still over TLS.
- The default security group has no rules, and the default VPC is deleted in the chosen region.
- Operators reach the database through ECS Exec or SSM Session Manager. There is no bastion host
  and no SSH.

## Data

- **Encryption at rest** with one customer-managed KMS key per environment, used by RDS,
  ElastiCache, the media bucket and Secrets Manager. The key policy lets the admin permission set
  manage it and the task roles, CloudFront (for media) and AWS Backup use it. Encryption is set
  when each resource is created: RDS and ElastiCache can't be encrypted afterwards without a
  snapshot and restore. The SPA bucket holds public files and keeps S3's default encryption.
- **Encryption in transit**, TLS 1.2 or later everywhere:
  - CloudFront redirects HTTP to HTTPS and sends HSTS. CloudFront reaches the ALB over HTTPS, and
    the ALB has no HTTP listener.
  - Both buckets' policies deny requests that aren't over TLS.
  - RDS sets `rds.force_ssl`, and Django connects with `sslmode=verify-full` and the RDS CA
    bundle.
  - ElastiCache has in-transit encryption and an AUTH token; Celery connects with `rediss://`.
- **Secrets.** RDS creates and rotates its own master password in Secrets Manager
  (`manage_master_user_password`). Terraform creates the other secrets empty; their values are set
  once with the AWS CLI and never pass through Terraform. The exceptions are the ElastiCache AUTH
  token and the CloudFront origin header, generated by Terraform and copied into Secrets Manager
  for the services. Using either needs a foothold inside the VPC or a CloudFront distribution of
  one's own, so a leak of state alone gives little. If state is exposed, a `rotate-secrets`
  workflow (`workflow_dispatch`, run with `ci-deploy` in the chosen environment) replaces both in
  order:
  1. generates new values (`terraform apply -replace` on both `random_password` resources), with
     ElastiCache's `ROTATE` strategy and the listener rule accepting the old and new values;
  2. redeploys the ECS services so they read the new token, and waits for CloudFront to deploy
     the new header;
  3. applies again with `SET` and the old header value removed, so the old values stop working.

  The CloudTrail record of state reads shows which identity read it, so that access can be
  revoked too. The workflow is tested once in staging.
- **Backups.**
  - RDS keeps automated backups with point-in-time recovery: 1 day in staging and 14 in prod.
    Prod has deletion protection and takes a final snapshot if destroyed.
  - In prod, AWS Backup copies a daily RDS snapshot to a locked vault in the management account,
    so someone who takes over the prod account can't delete every backup. The copy needs the
    customer-managed key, since snapshots under AWS's default RDS key can't leave the account.
  - The media bucket keeps object versions for 30 days. Regenerating lost media would cost users
    credits.

## Workers and secrets

Each ECS service has its own task role, and reads only its own secrets:

| Service | Secrets | Other access |
|---|---|---|
| `api` | Django, Stripe, CloudFront signing key | RDS, Redis, media bucket, SES |
| `worker` | Django, Anthropic | RDS, Redis, media bucket |
| `worker-tts` | Django, Speechify | RDS, Redis, media bucket |
| `worker-fetch` | its own database login | RDS (`fetch` role), Redis, media bucket |
| `beat` | Django | RDS, Redis, Cost Explorer (read) |

`worker-fetch` is the only service that requests URLs users supply, and it opens uploaded zips
(see [pipeline.md](pipeline.md#tasks-and-workers)). It is treated as the service most likely to be
taken over, so it gets as little as possible:
- **No Django `SECRET_KEY`.** Celery tasks sign nothing, so it runs with its own settings module
  and a throwaway key generated at startup. A takeover can't forge sessions.
- **Its own Postgres role**, `fetch`, granted only the tables the fetch and upload tasks use
  (such as `StageNode`, `StageRun` and `Lecture`), with no access to users, sessions or billing.
  It never gets the RDS master credentials.
- **No API keys.** The Anthropic, Speechify and Stripe keys are out of reach.
- **A nearly empty task role:** its one secret and its media bucket prefixes. The ECS
  credentials endpoint (169.254.170.2) is served to the task directly and security groups can't
  block it, so a missed SSRF check could read these credentials; with this role they grant
  almost nothing.

It still shares Redis with the other workers, so a takeover could queue tasks for `worker` or
`worker-tts`. Celery accepts only the JSON serializer (never pickle), and every task loads its
inputs from the database by node ID instead of trusting its arguments, so an injected task can at
most re-run a real node, charged to that node's owner as usual. Per-service ElastiCache RBAC users
would close this, but Celery's key layout makes per-queue ACLs fiddly, so it is recorded as a
residual risk. A provider that needs Claude during fetch (the M8 AI-agent provider) gets a scoped
key when it lands.

## Detection

- **CloudTrail:** one organization trail for management events in every account, written to the
  log bucket in the management account with Object Lock (one year) and versioning.
- **GuardDuty** in prod. It flags stolen credentials used outside AWS, crypto-mining, and
  connections to known-bad hosts. High and medium findings go through EventBridge to SNS, which
  emails the admin. Staging is mostly idle and doesn't run it.
- **CloudWatch Logs** have a retention period: 14 days in staging and 90 in prod.
- **AWS Budgets** alerts in each account, as a backstop for runaway spend from a leaked key or a
  bug. The cost dashboard in the private billing plan is the main view.

## Edge protection

- **Until prod:** Django throttles requests itself, with allauth's rate limits on sign-in,
  sign-up and password reset, and DRF throttles on the API (stricter on run creation and
  estimates).
- **Prod (M6):** AWS WAF on the prod CloudFront distribution with the AWS managed rule groups
  (core rule set, known bad inputs, IP reputation) and rate-based rules on `/api/auth/*` and run
  creation. Blocked traffic never reaches Fargate. Fake sign-ups don't earn credits (the trial
  grant needs a paid subscription), so WAF is mainly for sign-in attacks, sign-up spam (which
  costs SES sends and sender reputation) and bulk API traffic.

## CI checks

- **Checkov** scans `infra/terraform/` in `ci.yml`, alongside `terraform validate`. Skipped
  checks are listed in the code with a reason.
- **Dependabot** for uv, pnpm, GitHub Actions and the Dockerfiles.
- **ECR scanning** on push; findings rated critical are fixed before the next deploy.
- **Weekly image rebuilds**, deployed to staging, so OS packages stay patched without app changes.
- **OWASP ZAP baseline** scan against staging after each deploy, with the report kept as a
  workflow artifact. It reports only at first, and blocks on high-risk alerts once the baseline
  is clean.

## Public repo

The repo is public, so committed code names no specific account or resource:
- Committed Terraform has no AWS account IDs, ARNs containing them, or state bucket names, and
  no `*.tfvars` files. `.gitignore` covers `*.tfvars`, `*.tfstate*`, `.terraform/`, `.env`
  and Terraform's local override files; `.terraform.lock.hcl` stays committed.
- Terraform looks account IDs up at run time (`data "aws_caller_identity"`) wherever it can.
- CI reads account IDs, role ARNs and backend settings from variables on the `staging` and
  `prod` GitHub environments. Locally they come from `.env`, loaded by mise; that includes the
  `org` environment, applied by hand from the management account.
- **gitleaks** runs in `ci.yml` and fails on committed secrets and on 12-digit AWS account IDs
  under `infra/`. GitHub's secret scanning and push protection are on as well, and stop a known
  key format before it reaches the repo.

## Deferred

**Security Hub and AWS Config** check live infrastructure against benchmarks such as CIS. They
matter most when people change infrastructure by hand. Here, only CI changes it and Checkov checks
every PR. Config also charges for every recorded change, which ECS deploys and staging's scale to
zero would drive up. Revisit once prod has run for a few months, or when more people get access.

## Not adopted

| Recipe | Why not |
|---|---|
| A second organization for testing policies | One set of policies, tested in staging first |
| Separate log-archive and security-tooling accounts | The management account holds the logs and backups at this size |
| Transit Gateway, VPN and private endpoints between accounts | One VPC per environment, no on-premises network |
| Interface VPC endpoints | $40–60 a month across two AZs; the NAT gateway carries that traffic over TLS |
| AWS Private CA | About $400 a month; the ALB uses a public ACM certificate |
| Amazon Macie | Media is course material, not personal data |
| Systems Manager inventory and Patch Manager | No EC2 instances; image rebuilds cover patching |
| Permission boundaries and tag-based access | One operator, and no teams sharing an account |

## Costs

About $1–2 a month for staging (the KMS key and log storage). About $5 for prod (GuardDuty and the
KMS key), rising to about $15 when WAF is added at M6. Backup storage grows with the database.

## Verification

- Checkov passes in CI with every skip justified.
- In staging: creating a resource in another region is denied, a request straight to the ALB
  is rejected, a plain-HTTP S3 request is denied, and `psql` without SSL is refused.
- The policy simulator shows `worker-fetch`'s role can't read the Anthropic, Speechify, Stripe
  or Django secrets.
- In staging, `worker-fetch`'s `fetch` database role can't read or write tables outside its
  grants, such as users and sessions.
- A pull request's CI job can't assume `ci-deploy`.
- Reading the Terraform state bucket shows up in CloudTrail.
- The `rotate-secrets` workflow runs in staging without failed requests or Celery connection
  errors, and the old token and header are rejected afterwards.
- GuardDuty's sample findings reach the admin's email.
- Before prod launches, a database restored from the management account's vault into staging
  serves the site.
- The ZAP baseline reports no high-risk alerts.
