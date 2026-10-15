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
make db-upgrade
make dev
```

The Vue development server is at `http://localhost:5173`; it proxies `/api` to the FastAPI service at `http://127.0.0.1:8000`. API documentation is available at `http://127.0.0.1:8000/api/v1/docs`, with OpenAPI JSON at `http://127.0.0.1:8000/api/v1/openapi.json`.

The API process is the only process that accesses the database. All database access uses SQLAlchemy ORM sessions/connections. The development database defaults to `var/contestmaster.db`; Alembic owns schema changes.

## Privileged accounts and sessions

Apply migrations before bootstrapping the first global administrator. The one-time command prompts for a password without echoing it, requires confirmation and a 12-character minimum, and refuses to run after any system account exists:

```sh
uv run alembic upgrade head
uv run contestmaster-admin create-first-admin \
  --username admin \
  --email admin@example.org \
  --display-name "Site Administrator"
```

Passwords are stored as salted scrypt hashes. Sign in through `POST /api/v1/auth/login`; the API returns the current user's non-secret profile and sets a short-lived server-side session cookie (`HttpOnly`, `SameSite=Strict`) plus a CSRF cookie. Send the CSRF value in `X-CSRF-Token` for mutations. `POST /api/v1/auth/logout` revokes the server-side session. The session cookie is secure by default. `.env.example` turns `SECURE_COOKIES` off only for local plain-HTTP development; production configuration rejects that setting. A global administrator can provision contest-manager accounts through the protected `/api/v1/auth/admin/users` endpoint. Contest managers cannot create system accounts.

The Vue staff pages are `/sign-in` and `/manage/contests`. A manager creates a draft with its start, end, separate log cutoff, and automatic-recalculation setting. Contest times entered in the browser's local timezone are converted to UTC before they are sent to the API. Configure categories and other contest conditions in `/rulesets/compose`, validate and save that immutable ruleset version, then assign it to the draft in the contest manager. The API enforces ownership and allows ruleset activation only while a contest is a draft.

Participant access is at `/participant/access`. Set `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT` (STARTTLS, normally `587`), `EMAIL_SMTP_USERNAME`, `EMAIL_SMTP_PASSWORD`, and `EMAIL_FROM_ADDRESS` to enable verification/sign-in emails. `FRONTEND_BASE_URL` controls the destination for emailed links. SMTP credentials belong only in deployment secrets and must not be committed. The development `.env.example` intentionally leaves delivery unconfigured; without SMTP, magic-link requests return an unavailable response rather than exposing a token in the API or logs.

Administrative account provisioning, contest edits, ruleset version creation, and contest ruleset activation write append-only audit events in the same transaction as the change. The optional `audit_reason` request field records operator context; event metadata must never contain passwords, session/receipt tokens, uploaded log contents, or unnecessary personal information.

The API checks enabled master-data sources immediately on startup when any required active version is missing, then checks nightly at `MASTER_DATA_NIGHTLY_HOUR_UTC` (default `2`, UTC). Enabled sources currently include Big CTY, UNGEGN WGN country names/M49 identifiers, and the UNSD M49 country-or-area list. The M49 adapter stores published names and numeric codes as-is. Set `MASTER_DATA_SCHEDULER_ENABLED=false` only for one-shot or test processes. Run all adapters from CLI with `uv run contestmaster-master-data sync`, or one with `sync-cty`, `sync-ungegn`, or `sync-m49`; inspect recent runs and active versions with `uv run contestmaster-master-data status`. The API exposes basic provisioning status at `/api/v1/master-data/status`.

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
