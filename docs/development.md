# Local development

Run all commands from the repository root unless a step changes the directory.
The current scaffold requires Python 3.13, Node.js 24, and npm. Version hints are
in `.python-version` and `.nvmrc`. Docker and paid services are not required.

## Setup

Clone the repository with your normal GitHub access:

```sh
git clone https://github.com/giorgioinfo13/tech-news-radar.git
cd tech-news-radar
```

Create local configuration and the Python environment:

```sh
cp .env.example .env
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
```

Install frontend dependencies from the lockfile:

```sh
cd frontend
npm ci
```

Use Python 3.13 when you create the virtual environment. The backend dependency
range intentionally matches that version until other Python versions are tested.

## Initialize the database

From the repository root, apply the migrations:

```sh
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic check
```

With the default configuration, this creates `backend/data/news.db` and eight
editable categories. No sources or articles are imported. The expected revision is
`0001 (head)`, with no pending schema changes.

Run `alembic upgrade head` after updates that add migrations. Repeating it on an
up-to-date database preserves category edits and existing data. The API does not
create tables or apply migrations at startup. The database directory is ignored by Git.

`TNR_DATABASE_URL` controls the database location. Relative SQLite paths resolve
from `backend/`, even if the command runs from another directory. Absolute SQLite
paths are supported. SQLite URI mode (`uri=true`) is not supported.

For a command from the repository root, specify the config explicitly:

```sh
backend/.venv/bin/alembic -c backend/alembic.ini current
```

Schema changes need a new revision. From `backend/`, run
`.venv/bin/alembic revision --autogenerate -m "describe the schema change"`, then
review the generated operations and add migration tests. Do not rewrite shared revisions.
The initial migration's downgrade removes all application tables and data; use it
only with a disposable database. Tests exercise this path in temporary directories.

## Run the backend

In one terminal, start from the repository root:

```sh
cd backend
.venv/bin/python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

- Health: <http://127.0.0.1:8000/api/health>, with response `{"status":"ok"}`.
- API documentation: <http://127.0.0.1:8000/docs>.
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>.

The health endpoint reports process availability, not database readiness.
The database schema is available, but management endpoints are not implemented yet.

## Run the frontend

In a second terminal, start from the repository root:

```sh
cd frontend
npm run dev
```

Open <http://127.0.0.1:5173>. The current page introduces the project.
Vite forwards `/api` requests to the backend, so
<http://127.0.0.1:5173/api/health> returns the same health response.
Stop each server with `Ctrl+C`.

Both servers bind to loopback. Keep them local: authentication is not implemented.
If a configured port is occupied, stop the conflicting process or choose a new
port explicitly. If you change the backend port, update `TNR_API_TARGET` too.

## Configuration

Copy `.env.example` to the repository root as `.env`. Defaults work without that
file. Restart the development servers after configuration changes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TNR_APP_NAME` | `Tech News Radar` | Backend OpenAPI title |
| `TNR_DOCS_ENABLED` | `true` | Enable `/docs` and `/openapi.json` |
| `TNR_DATABASE_URL` | `sqlite:///data/news.db` | Database URL; relative SQLite paths start from `backend/` |
| `TNR_API_TARGET` | `http://127.0.0.1:8000` | Backend target for the Vite development proxy |

Process environment variables override `.env`. Do not store secrets in `VITE_*`
variables: Vite can include them in browser assets. Keep `.env` out of Git.

## Checks

Backend, from `backend/`:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pip check
```

Frontend, from `frontend/`:

```sh
npm run lint
npm run build
```

The build includes `npm run typecheck`. Frontend behavior tests will accompany
interactive features. The static introduction has no snapshot test suite.
Backend tests use an in-process HTTP client and temporary SQLite databases initialized
through Alembic. They require no external news services and do not change the local
development database. Migration tests also check schema/model consistency and repeated upgrades.

To inspect the frontend build, run `npm run preview` from `frontend/`.
Open <http://127.0.0.1:4173>. This previews static assets only; it does not provide
the development API proxy or a production deployment setup.

## Dependency updates

Commit dependency definitions and generated locks together when authorized.
Do not edit generated lockfiles manually.

Backend runtime and development dependencies are defined in `backend/pyproject.toml`.
`requirements.txt` locks runtime dependencies; `requirements-dev.txt` locks runtime
and test dependencies together. Both include hashes.

From `backend/`, install the pinned lock-generation tool and regenerate both locks:

```sh
.venv/bin/python -m pip install -r requirements-tooling.txt
.venv/bin/pip-compile --generate-hashes --strip-extras --output-file=requirements.txt pyproject.toml
.venv/bin/pip-compile --generate-hashes --strip-extras --extra=dev --constraint=requirements.txt --output-file=requirements-dev.txt pyproject.toml
```

Use `--upgrade-package PACKAGE` for an intentional package update. Review the
result and install the development lock before checks. Keep runtime pins aligned
between the two locks.

For frontend updates, run `npm install --save-exact PACKAGE@VERSION` from `frontend/`.
Use `--save-dev` for development tools. Review `package.json` and `package-lock.json`.

The frontend temporarily overrides the lint tools' `minimatch` dependency to
`11.0.1`, the patched version for
[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
This crosses the upstream dependency's major-version range. Lint and build checks
cover this scaffold, not every glob pattern. Remove the override when upstream
packages accept a patched version, then rerun the checks and `npm audit`.

## Contribution workflow

Keep changes small and scoped. Use `main` as the primary branch and short-lived
feature branches after initialization. Describe the change and its validation in
each pull request. Keep the two README versions equivalent.

Do not commit local databases, credentials, environment files, generated assets,
or virtual environments. Preserve the project's [MIT License](../LICENSE) and any
applicable third-party notices.
