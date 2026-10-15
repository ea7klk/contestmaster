# Local development

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

The API checks Big CTY immediately on startup when no active CTY version exists, then checks nightly at `MASTER_DATA_NIGHTLY_HOUR_UTC` (default `2`, UTC). Set `MASTER_DATA_SCHEDULER_ENABLED=false` only for one-shot or test processes. The same importer can run once from CLI with `uv run contestmaster-master-data sync`; inspect recent runs and active versions with `uv run contestmaster-master-data status`. The API exposes basic provisioning status at `/api/v1/master-data/status`.

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
