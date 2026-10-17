# Local development

## Project license

Contestmaster's original source code is licensed under the GNU Affero General Public License version 3 only (SPDX: `AGPL-3.0-only`). See the repository's [`LICENSE`](../../LICENSE) and [`COPYRIGHT`](../../COPYRIGHT) files. Under AGPL section 13, operators of a modified version offered for remote network interaction must provide those users access to the corresponding source. The license applies to project-authored software; external master data, contest rules, and other third-party materials remain subject to their own terms.

## Requirements

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/).
- Node.js 24 (see `.nvmrc`) and npm. [nvm](https://github.com/nvm-sh/nvm) is the recommended per-user Node version manager. On macOS/Linux, install nvm using its official installer, then run `nvm install` and `nvm use` in the repository. A direct Node.js 24 installation is also supported.
- Git and Make.

Project Python dependencies are installed into the repository's `.venv` using the committed `uv.lock`; frontend dependencies are installed from `frontend/package-lock.json` using `npm ci`. Do not install project packages globally.

## Bootstrap and run

```sh
# Install uv using the official installer if it is not available.
curl -LsSf https://astral.sh/uv/install.sh | sh

# If using nvm, load it in this shell first, then select the checked-in Node version.
nvm install
nvm use

cp .env.example .env
make setup
make dev
```

The Vue development server is at `http://localhost:5173`; it proxies `/api` to the FastAPI service at `http://127.0.0.1:8000`. API documentation is available at `http://127.0.0.1:8000/api/v1/docs`, with OpenAPI JSON at `http://127.0.0.1:8000/api/v1/openapi.json`.

The API process is the only process that accesses the database. All database access uses SQLAlchemy ORM sessions/connections. The development database defaults to `var/contestmaster.db`; Alembic owns schema changes. Before serving requests, API startup applies pending migrations. New databases use one consolidated current-schema baseline; every later data-model change is a separate Alembic revision above it. Historical revisions are retained in a compatibility-only archive so databases from before the squash can be upgraded without losing records. The consolidated baseline intentionally shares its revision ID with the last archived revision; startup applies active forward migrations to databases already at that revision, and migration tests cover that compatibility path. The recurring-series revision adds its nullable contest reference in place instead of rebuilding `contests`, preserving foreign-key references from existing entries and contest history; the migration test covers upgrade, downgrade, and re-upgrade with retained data.

### Guest log submission

The Vue upload workflow is available at `/submit-log`. It uploads multipart Cabrillo or ADI/ADIF files enabled by the contest ruleset to the public API and reports progress, import counts, line-level errors, and warnings. No privileged account is required. A successful upload displays the entry-scoped receipt token once; save it privately to edit or resubmit that entry. The original text and each accepted revision are retained in SQLite alongside normalized ORM-managed station and QSO rows.

After accepted ADI/ADIF uploads, guests can optionally submit an email address with separate entry-access and published-result notice choices. Cabrillo uploads show this prompt only when no valid `EMAIL` header is present. A valid Cabrillo address triggers entry-access verification only; it does not enable result notices. Email identities remain entry-scoped and unverified until a one-time link is consumed. Guest delivery uses Mailcow SMTP configuration and a retryable publication outbox; declining email does not change or block receipt-token access.

The API accepts UTF-8 Cabrillo 2.0/3.0 `.log`, `.cbr`, `.cabrillo`, and `.txt` files and text ADI/ADIF `.adi`/`.adif` files up to 5 MiB, with up to 64 KiB multipart overhead. The contest's ruleset mapping determines which formats are accepted, and the upload page lists them. Log creation and resubmission have no application rate limit. Exact retries use the same `Idempotency-Key` and file content and return the same entry receipt without creating duplicate revisions. Production `ENTRY_RECEIPT_SECRET` must contain at least 32 random bytes and remain stable across restarts. Never commit this secret. See [supported log formats](../formats/README.md) for supported fields and compatibility limits.

Malformed logs are rejected as a whole with source-line diagnostics. Unknown header values, extra Cabrillo columns, and unrecognized ADIF QSO fields are preserved for review. Corrections append immutable `entry_revisions`; contact edits never overwrite earlier input. A valid receipt token or the associated verified participant session is required for entry details and corrections. Contest Admins can expire, revoke, or rotate guest grants from their contest workflow.

## Privileged accounts and sessions

Start the API once so it can initialize or upgrade the database before bootstrapping the first global administrator. The one-time command prompts for a password without echoing it, requires confirmation and a 12-character minimum, and refuses to run after any system account exists:

```sh
make start-api
uv run python -m backend.app.identity_cli create-first-admin \
  --username admin \
  --email admin@example.org \
  --display-name "Site Administrator"
```

Passwords are stored as salted scrypt hashes. Sign in through `POST /api/v1/auth/login`; the API returns the current user's non-secret profile and sets a short-lived server-side session cookie (`HttpOnly`, `SameSite=Strict`) plus a CSRF cookie. Send the CSRF value in `X-CSRF-Token` for mutations. `POST /api/v1/auth/logout` revokes the server-side session. The session cookie is secure by default. `.env.example` turns `SECURE_COOKIES` off only for local plain-HTTP development; production configuration rejects that setting. Global Administrators can provision and manage both privileged roles through `/api/v1/auth/admin/users`, and manage participant account status through `/api/v1/auth/admin/participants`. Contest Admin accounts have scoped rights only to contests and rulesets they own or were assigned.

The Vue staff pages are `/sign-in`, `/manage/contests`, and `/manage/rulesets`. Both management pages are server-paged and filterable. Create/edit contests at `/manage/contests/new` and `/manage/contests/{contest_id}/edit`; a manager enters UTC start/end instants, optional periodicity, a separate UTC log cutoff, and the automatic-recalculation setting. Recurring contests are independent editions attached to a series. The editor previews five UTC dates, optionally creates editions within a configurable 1–730 day rolling window, manages skip/move exceptions, and supports series-level cutoff offsets with per-edition absolute overrides. The API timer is enabled with `CONTEST_SCHEDULER_ENABLED` and runs at `CONTEST_SCHEDULER_INTERVAL_SECONDS` (default 3600 seconds). Removing a series requires typing its exact name and deletes all editions and their dependent contest data. Create a ruleset at `/manage/rulesets/new`; start a new immutable version from a saved ruleset at `/manage/rulesets/{version_id}/edit`. The ruleset composer contains reusable categories and contest conditions, but no event dates, periodicity, or cutoff instant. Validate and save that immutable ruleset version, then assign it to a draft in the contest listing. A global administrator manages band and mode choices in separate sections on `/admin/operating-catalog`; each section has its own add form. See [ruleset composer guidance](../ruleset-composer/README.md). The API enforces ownership and allows ruleset activation only while a contest is a draft.

Participant access is at `/participant/access`. Participants can register with a callsign, email, and password; the email must be verified before password login. The profile supports additional callsigns, display-name updates, associated entry management, withdrawal, and two-address email changes. Account recovery links are single-use and expiring. Existing email magic links remain available. Set `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT` (STARTTLS, normally `587`), `EMAIL_SMTP_USERNAME`, `EMAIL_SMTP_PASSWORD`, and `EMAIL_FROM_ADDRESS` to enable verification/sign-in emails. `FRONTEND_BASE_URL` controls the destination for emailed links. SMTP credentials belong only in deployment secrets and must not be committed. The development `.env.example` intentionally leaves delivery unconfigured; without SMTP, email requests return an unavailable response rather than exposing a token in the API or logs. See the [Mailcow SMTP setup](../operations/README.md#mailcow-smtp-example) for the selected `mail.conxtor.com` example.

Administrative account provisioning, contest edits and status changes, ruleset version creation/activation, guest grant changes, and master-data version activation/deletion write append-only audit events in the same transaction as the change. The optional `audit_reason` request field records operator context; event metadata must never contain passwords, session/receipt tokens, uploaded log contents, or unnecessary personal information.

Global administrators can inspect master-data versions and recent sync attempts at `/admin/master-data`. They can activate a validated candidate or delete only an unreferenced candidate/retired version. Deletion keeps source sync runs and appends an audit event; the API and SQLite reject active or retained-reference deletions.

The API checks for an active Big CTY version on startup and checks CTY nightly at `MASTER_DATA_NIGHTLY_HOUR_UTC` (default `2`, UTC). When no active CTY version exists, the initial import starts immediately in the background after migrations; it does not delay API startup. Liveness and database readiness do not mean master data is ready: inspect `/api/v1/master-data/status` and wait for an active version before running scoring that depends on CTY. Startup logs identify the sync trigger and each source request, including start, completion, response size, duration, and failure. Big CTY `cty.dat` is the only provisioned master-data source. Set `MASTER_DATA_SCHEDULER_ENABLED=false` only for one-shot or test processes. Run the one-shot import with `uv run contestmaster-master-data sync` or `uv run contestmaster-master-data sync-cty`; inspect recent runs and active versions with `uv run contestmaster-master-data status`. Contest exchanges and rulesets supply contest-specific sections, grids, serials, and other identifiers.

## Useful commands

| Command | Purpose |
|---|---|
| `make setup` | Install locked Python and JavaScript dependencies |
| `make dev` | Start the API and Vue development server |
| `make api` / `make frontend` | Start one development service |
| `make test` | Run backend and frontend unit tests |
| `make lint` | Run Python linting, ESLint, and TypeScript checking |
| `make format` | Format backend and frontend source |
| `make db-upgrade` | Apply Alembic migrations to configured database |

The supported local versions are Python 3.12 and Node.js 24. `uv sync --locked --group dev` creates and maintains `.venv` from `uv.lock`; `npm ci` installs exactly from the frontend lockfile.
