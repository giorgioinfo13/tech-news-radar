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
Apply migrations before you use the management endpoints. A missing schema causes
database requests to fail, even when the health check succeeds.

## Use the REST API

Use `/docs` to inspect request schemas and try the endpoints against your local database.
These operations change persistent data. Authentication is not implemented.

| Method | Path | Behavior |
| --- | --- | --- |
| `GET`, `POST` | `/api/categories` | List or create categories |
| `PATCH`, `DELETE` | `/api/categories/{id}` | Edit or delete a category |
| `GET`, `POST` | `/api/sources` | List or create source configurations |
| `PATCH`, `DELETE` | `/api/sources/{id}` | Edit or delete a source |
| `GET` | `/api/sources/{id}/runs` | List a source's collection history |
| `GET` | `/api/articles` | List, filter, and search articles |
| `PATCH` | `/api/articles/{id}` | Set read/unread status |

All list endpoints return `items`, `total`, `limit`, and `offset`. The default limit
is 50, with a maximum of 100. Offset starts at zero. Total counts all matching items,
before pagination. Categories sort by `sort_order` then ID. Sources sort by name then ID.
Articles sort newest first, using acquisition time when publication time is unknown.
Collection history sorts by start time. Descending IDs break article and history ties.

Source filters are `category_id` and `enabled`. Article filters are `source_id`,
`category_id`, `is_read`, and `q`. Filters combine. Search checks titles and descriptions
for a literal substring, with SQLite's case handling. `%` and `_` are literal characters.
An empty or whitespace-only search applies no text filter. Categories in article responses
reflect the source's current category. Disabled sources' existing articles remain visible.

Create a category with `{"name":"Custom","slug":"custom","sort_order":0}`.
Slugs use lowercase ASCII letters, digits, and single hyphens between groups.
Create a source with `{"name":"Example","feed_url":"https://example.org/feed.xml"}`.
This is a placeholder URL, not a verified feed. Optional source fields are `category_id`,
`enabled` (default `true`), and `refresh_interval_minutes` (default 60, range 1–10080).
The interval is stored for the future scheduler and has no operational effect yet.

PATCH changes only supplied fields. An empty category/source PATCH preserves all values.
Use `{"category_id":null}` to remove a source's category. Other editable fields cannot
be null. Set article read status with `{"is_read":true}` or `{"is_read":false}`.
Unknown input fields are rejected. Diagnostic fields and timestamps are read-only.
Validation failures return `422`, missing records return `404`, and uniqueness conflicts
return `409`. A nonexistent category in a source request returns `404`.
Creation returns `201`, updates return `200`, and deletion returns `204` without a body.

Deleting a category leaves its sources uncategorized and preserves articles.
Deleting a source permanently deletes its articles and collection history.
Changing a source URL preserves that history but clears cache validators and current errors.
URLs must use HTTP/HTTPS without credentials or fragments. Saving a URL does not
verify that it provides a feed. RSS collection and manual refresh are not available yet.
Article and history lists remain empty until the future collector imports data.

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

Keep changes small and scoped. Current maintainer work uses `main` directly.
External contributors can submit pull requests from their forks. Describe the change
and its validation in each pull request. Keep the two README versions equivalent.

Do not commit local databases, credentials, environment files, generated assets,
or virtual environments. Preserve the project's [MIT License](../LICENSE) and any
applicable third-party notices.
