# Operations guide

This guide covers the first single-host deployment: one API process, one local SQLite database, and the API's internal UTC master-data timer. Keep the database on persistent local storage. Do not run multiple API workers or replicas while rate limits and scheduling are process-local.

## Runtime configuration

Configuration is read from the process environment or `.env` in the working directory. Keep `.env` outside source control and restrict it to the service account (`0600` where supported). `.env.example` lists development defaults.

| Variable | Default | Production/staging requirement | Secret |
| --- | --- | --- | --- |
| `APP_ENV` | `development` | Set to `staging` or `production`; only development, test, staging, and production are accepted. | No |
| `DATABASE_URL` | `sqlite:///./var/contestmaster.db` | File-backed SQLite on durable local disk; keep write access limited to the service account. | No |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | Positive integer; tune only after measuring lock contention. | No |
| `API_PREFIX` | `/api/v1` | Keep the published API version prefix. | No |
| `LOG_LEVEL` | `INFO` | Use `INFO` or `WARNING` in normal operation. | No |
| `ALLOWED_ORIGINS` | `["http://localhost:5173"]` | Exact HTTPS frontend origins; wildcard origins are rejected. | No |
| `SECURE_COOKIES` | `true` | Must remain enabled in staging/production; terminate HTTPS before the API. | No |
| `EMAIL_SMTP_HOST` | unset | Required for staging/production email magic links and account recovery. | No |
| `EMAIL_SMTP_PORT` | `587` | Set to the provider's submission port. | No |
| `EMAIL_SMTP_USERNAME` | unset | Set if required by the SMTP provider. | Sometimes |
| `EMAIL_SMTP_PASSWORD` | unset | Store in the host's secret facility; rotate at the provider and restart the service. | Yes |
| `EMAIL_FROM_ADDRESS` | unset | Required in staging/production and authorized by the mail provider. | No |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | Public HTTPS origin used in email links. | No |
| `ENTRY_RECEIPT_SECRET` | development placeholder | Generate a unique random value of at least 32 bytes. Rotating it invalidates deterministic receipt-token replay behavior; coordinate rotation and notify operators. | Yes |
| `MASTER_DATA_SCHEDULER_ENABLED` | `true` | Must be enabled in staging/production. The API imports Big CTY immediately on startup if no active CTY version exists, then checks it nightly. | No |
| `MASTER_DATA_NIGHTLY_HOUR_UTC` | `2` | Integer UTC hour from 0 through 23. | No |
| `METRICS_ENABLED` | `false` | Enable only when a trusted local monitor can scrape the endpoint. | No |
| `METRICS_BEARER_TOKEN` | unset | At least 32 random bytes when metrics are enabled. Rotate the token and monitor configuration together. | Yes |

Generate secrets with an operating-system cryptographic generator, for example `openssl rand -base64 48`. Do not paste secret values into issues, shell transcripts, logs, or support tickets. The metrics route returns 404 while disabled and requires a bearer token when enabled. Restrict it at the reverse proxy/firewall as well.

## Start, readiness, and provisioning

Install the pinned tools and dependencies with `make setup`, then start exactly one API process with `make start-api`. API startup applies pending Alembic migrations before serving requests and aborts startup if migration fails. New databases use one consolidated baseline; each later data-model change is a separate Alembic migration above it. A compatibility-only archive upgrades databases stamped at a pre-squash revision. `make db-upgrade` remains available for explicit preflight or maintenance runs. Serve the built Vue application from an HTTPS-capable reverse proxy or static host and proxy `/api/` to the API. Keep proxy request limits at least as restrictive as the application's 1 MiB JSON and 5 MiB + 64 KiB multipart limits.

After the first startup has completed its database migration, create the initial administrator interactively so the password is not passed as a command argument: `uv run contestmaster-admin create-first-admin --username admin --email admin@example.org --display-name "Contestmaster Administrator"`. Run it before exposing the service. The command refuses to create another initial account once any system user exists. A global administrator creates later contest-manager accounts through the administration API/UI.

Use `GET /api/v1/health/live` for process liveness and `GET /api/v1/health/ready` for database readiness. These endpoints become available after database migrations; they do not signal that CTY master data is ready. If no active CTY version exists, the API starts the initial import immediately in the background without delaying startup. Check `GET /api/v1/master-data/status` for active versions and the latest provisioning attempt, and wait for the required version before running scoring that depends on CTY. Startup logs show the provisioning trigger and source-request start, completion, duration, response size, and failures. The global-admin interface provides detailed version operations. The standalone importer remains available through `uv run contestmaster-master-data sync`; `status` prints recent runs and active versions. The same command can later be called by a K3s CronJob as a one-shot Job.

The internal scheduler and in-process rate limiter require one API process. Process supervision (systemd, a container supervisor, or equivalent) should restart a failed process and retain its logs. Configure a graceful shutdown timeout so in-flight requests finish before restart.

## Database backup and restore

**Stop the API before backup or restore.** These commands are deliberately offline operations. They checkpoint SQLite's write-ahead log through SQLAlchemy, copy the database, and verify the copy with SQLite's integrity check. Never copy only the main database file while the API is running.

```sh
uv run contestmaster-db verify
uv run contestmaster-db backup /secure-backups/contestmaster-2026-10-15.db
uv run contestmaster-db restore /secure-backups/contestmaster-2026-10-15.db
uv run contestmaster-db verify
```

Backups are not overwritten. Restore validates the source before touching the configured database, preserves an existing target as `*.pre-restore-<UTC timestamp>.bak`, stages a second copy, validates it, and atomically replaces the configured file. Keep the API stopped throughout. Protect backups like production data because they contain participant contact details, original submitted logs, and account data; encrypt storage and limit access. Define a retention schedule that meets the operator's legal and contest-retention obligations, then securely delete expired copies.

Set a backup cadence appropriate to the contest calendar. The RPO is the interval since the last successfully verified backup; the application does not yet automate backups or guarantee zero data loss. Record backup timestamp, checksum, destination, and verification outcome in an access-controlled operations log. Periodically restore a backup to an isolated staging path and check readiness before relying on it.

## Schema upgrades and rollback

1. Read the separate migration diff and release notes; schedule downtime and notify users if uploads or contest administration will be unavailable.
2. Stop the API and create a verified pre-upgrade backup.
3. Install locked dependencies. Optionally run `make db-upgrade` as a preflight; normal startup applies all pending migrations.
4. Start one API process, then run `uv run contestmaster-db verify`, check liveness/readiness and master-data status, and run smoke checks.
5. If an upgrade fails, startup aborts. Keep the API stopped and preserve the failed database for diagnosis. Prefer a forward-fix migration. Do not assume `alembic downgrade` is data-safe; use it only when the specific migration explicitly supports downgrade and it has been exercised against a copy. Otherwise restore the pre-upgrade backup, apply a corrected release, and verify it before reopening service.

Schema rollback does not roll back external emails, published snapshots already downloaded by users, or actions recorded in external systems. Record the chosen recovery path and the resulting database revision.

## Logs, privacy, and retention

Application logs are structured JSON records with request IDs, method, path, status, duration, event names, and safe identifiers. Exception messages and tracebacks are intentionally omitted from client responses and server logs where they could echo untrusted input. Never log passwords, reset/magic-link URLs, session cookies, entry receipt tokens, idempotency keys, full log contents, participant email, or SMTP credentials. Restrict log access to operators who need it; configure host-level rotation and deletion according to the deployment's retention policy. Redact proxy access logs too, especially query strings on one-time-token pages. The frontend sets `Referrer-Policy: no-referrer`.

Recommended initial diagnostic-log retention is 30 days, with daily rotation, compression, and access limited to operators. Because the API writes to stdout, enforce this at the chosen process supervisor/container log driver; Contestmaster does not currently expire host logs itself. Original Cabrillo revisions, participant contact data, audit records, and immutable scoring/publication history are application records, not diagnostic logs. They currently have no automatic time-based purge; decide and publish their retention/deletion schedule before production based on contest rules and applicable privacy obligations. Do not delete data that is required to explain a published result or reproduce a historical score run.

## Metrics and alerts

Prometheus scrape configuration, low-cardinality alert rules, and a starter dashboard are in [`ops/observability`](../../ops/observability/). Scrape `/internal/metrics` over a trusted network and supply the configured bearer token. The endpoint intentionally excludes callsigns, account identifiers, tokens, filenames, and contest IDs. The metrics are process-local counters, so a process restart resets counter totals; master-data last-attempt/success timestamps are process metrics and should be compared with the persisted provisioning status endpoint. The starter alert thresholds need adjustment to the deployment's scrape interval and contest activity.

## Incident runbooks

### Credential or token compromise

Disable or reset the affected account, invalidate sessions/magic links through the account workflows, rotate compromised SMTP/metrics/receipt secrets, and restart the service. Review audit events and access logs for a bounded time window. Do not put the compromised token in the incident ticket. Notify affected participants when required by the deployment's incident policy.

### Database corruption or accidental deletion

Stop the API to prevent further writes. Preserve a copy of the damaged files for diagnosis, choose the newest known-good verified backup, restore it to the configured location, run `contestmaster-db verify`, and start the API. Check readiness, current Alembic revision, active master-data versions, latest score runs, and published result snapshots. Record the backup's recovery point and any uploads after it that must be resubmitted.

### Failed or partial master-data refresh

Inspect `/api/v1/master-data/status`, `contestmaster-master-data status`, and alert/dashboard history. A failed or ambiguous import must leave the last good active version intact. Resolve source availability or data validation issues, then rerun `uv run contestmaster-master-data sync`. If the contest rules consume callsign-derived facts, confirm an active CTY version covers the contest-start instant before generating scores. Do not manually replace files or activate an unreviewed partial import.

### Failed scoring or publication

Use the manager's score-run detail and audit history to identify the failed input revision, ruleset version, pinned master-data versions, and error class. Correct the underlying rule/input or restore required master data, then create a new run. Do not edit historical score runs or change a published snapshot in place. Publish a new immutable result snapshot after review.

### Service outage

Check supervisor status, disk space, process logs, liveness/readiness, database permissions, and reverse-proxy TLS/upstream health. Restart one API process after capturing relevant logs. If startup is delayed by initial master-data provisioning, inspect sync status before repeatedly restarting. If recovery requires a database restore, follow the corruption procedure.

## Local staging acceptance

The repository currently has no external staging host or production credentials. Before release, use a separately configured local staging database and run the complete backend API tests plus frontend workflow tests. They exercise administrator provisioning/authentication, contest ownership, guest log upload, scoring, publication, public standings, and privacy denial. Verify backup restoration into a separate staging database with the CLI tests. Record host/runtime, commit, exact commands, outcomes, and any skipped external checks in the Phase 9 tracking issues. This is local staging evidence, not a claim of a production deployment or external SMTP/monitor integration test.
