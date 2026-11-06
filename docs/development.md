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
`0004 (head)`, with no pending schema changes. Revision `0003` adds personal subscriptions and read states.
It preserves existing sources, categories, articles, and collection history. Existing read flags belong only to the reserved local owner.
Revision `0004` adds explicit Supabase identity links without changing existing profiles or personal data.
SQLite must be version 3.35 or later for the native column removal. Check the SQLite library bundled with your Python installation.

Run `alembic upgrade head` after updates that add migrations. Repeating it on an
up-to-date database preserves category edits and existing data. The API does not
create tables or apply migrations at startup. The database directory is ignored by Git.

`TNR_DATABASE_URL` controls the database location. Relative SQLite paths resolve
from `backend/`, even if the command runs from another directory. Absolute SQLite
paths are supported. SQLite URI mode (`uri=true`) is not supported.

SQLite remains the default and needs no cloud account. PostgreSQL uses the same models, APIs, collector, and scheduler.
See [PostgreSQL setup and isolated tests](postgresql.md) for TLS, schema isolation, and migration credentials.
Changing the URL does not copy data between databases.

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

For account-free local development, add these lines to your private root `.env` after applying the migrations:

```dotenv
TNR_LOCAL_USER_ID=00000000-0000-0000-0000-000000000001
VITE_LOCAL_MODE=true
```

This selects the reserved local administrator. It is not authentication and must not be enabled in a public deployment.
Omit all Supabase settings in this local mode. Without a local identity or Supabase configuration, data endpoints return `401`.
Health and API documentation remain available. The frontend local mode works only in a development build on a loopback hostname.
Google login and operator-approved access require the [authentication configuration](authentication.md).
See [multiuser behavior](multiuser.md) for roles and migration details.

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
These operations change persistent data. The local identity adapter is for loopback development only.
The backend requires an active application user and checks permissions on each request.
Only administrators can create, edit, or delete categories and sources.

| Method | Path | Behavior |
| --- | --- | --- |
| `GET`, `POST` | `/api/categories` | List or create categories |
| `PATCH`, `DELETE` | `/api/categories/{id}` | Edit or delete a category |
| `GET`, `POST` | `/api/sources` | List or create source configurations |
| `PATCH`, `DELETE` | `/api/sources/{id}` | Edit or delete a source |
| `POST` | `/api/sources/{id}/refresh` | Collect an enabled source and return the result |
| `GET` | `/api/sources/{id}/runs` | List a source's collection history |
| `GET` | `/api/articles` | List, filter, and search articles |
| `PATCH` | `/api/articles/{id}` | Set read/unread status |
| `GET` | `/api/me` | Read the current user's identity and role |
| `GET` | `/api/subscriptions` | List the current user's followed sources |
| `PUT`, `DELETE` | `/api/subscriptions/{source_id}` | Follow or unfollow a source for the current user |

All list endpoints return `items`, `total`, `limit`, and `offset`. The default limit
is 50, with a maximum of 100. Offset starts at zero. Total counts all matching items,
before pagination. Categories sort by `sort_order` then ID. Sources sort by name then ID.
Articles sort newest first, using acquisition time when publication time is unknown.
Collection history sorts by start time. Descending IDs break article and history ties.

Source filters are `category_id` and `enabled`. Article filters are `source_id`,
`category_id`, `is_read`, `q`, and `subscribed_only`. Filters combine.
Articles default to followed sources. Set `subscribed_only=false` to browse the shared archive.
Read status and its filters always apply to the current user, including for administrators.
Search checks titles and descriptions
for a literal substring. ASCII letters match without case sensitivity on both databases.
Non-ASCII case variants remain distinct. `%` and `_` are literal characters.
An empty or whitespace-only search applies no text filter. Categories in article responses
reflect the source's current category. Disabled sources' existing articles remain visible.

Create a category with `{"name":"Custom","slug":"custom","sort_order":0}`.
Slugs use lowercase ASCII letters, digits, and single hyphens between groups.
Create a source with `{"name":"Example","feed_url":"https://example.org/feed.xml"}`.
This is a placeholder URL, not a verified feed. Optional source fields are `category_id`,
`enabled` (default `true`), and `refresh_interval_minutes` (default 60, range 1–10080).
The scheduler uses this interval after the last completed check, including manual refreshes.
Change it through `/docs` or the REST API. The frontend does not yet expose this field.

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
verify that it provides a feed. Use manual refresh to collect its articles.

## Refresh a feed

Start the backend with one worker, as shown above. Do not run another backend process
against the same database. Update the virtual environment after dependency changes:

```sh
backend/.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
```

From `/docs`, create a source with a known RSS/Atom URL. Copy its returned `id`.
Call `POST /api/sources/{id}/refresh` without a request body. The request waits for completion.
Use `GET /api/articles?source_id={id}` to inspect imported articles.
Use `GET /api/sources/{id}/runs` to inspect collection history.

| HTTP result | Meaning |
| --- | --- |
| `200`, status `success` | Feed parsed and new articles saved |
| `200`, status `not_modified` | Conditional request returned `304`; existing articles preserved |
| `502`, status `error` | Collection failed; body contains the stored run and a safe error message |
| `404` | Source does not exist |
| `409` | Source is disabled, or another refresh/source change holds the collection lock |
| `429` | Cooldown active; `Retry-After` gives the remaining seconds |

Successful runs return `articles_seen` and `articles_added`. Their difference includes
duplicates and skipped invalid entries. Existing articles and read status are preserved.
Errors appear in both the run history and the source's `last_error` field.
After a failure, `last_success_at` retains the previous successful check time.
If the process stops during collection, its run stays `running` until that source is refreshed again.

Wait at least 30 seconds between successful refreshes of the same source. Failure
cooldowns start at 60 seconds and double up to one hour. Refresh does not wait or queue
another job when the collector is busy. Source edits and deletions also return `409`
during collection. Creating sources and reading articles remain available.

Only public HTTP/HTTPS destinations on ports 80/443 are supported. The collector checks
DNS answers and redirects, verifies TLS certificates, and ignores environment proxies.
It requests uncompressed content and also accepts gzip within the same decoded-size limit.
Other compression formats and concatenated gzip streams are rejected.
Malformed XML, DTDs, entities, excessive nesting, and oversized feeds are rejected.
An HTTP timeout does not impose a hard deadline on the OS DNS resolver.
See [collection architecture](architecture.md#manual-collection) for limits and tradeoffs.

Sources are not installed automatically. The optional catalog command below imports verified feeds.
New sources are not followed automatically. Select them in **Le mie fonti**, or use `PUT /api/subscriptions/{source_id}` in `/docs`.
Existing sources are followed once for the local owner during migration `0003`.
Automatic collection uses the same guarded collector and history as manual refresh.
The frontend uses these endpoints and does not require a new database migration.

## Automatic collection

Apply migrations before you start the backend. Use one process and one worker per database.
The scheduler starts with the backend and waits 30 seconds before its first scan.
It checks enabled sources, with never-checked and older sources first.
Each source has a default interval of 60 minutes, measured from its last completed check.
New enabled sources become eligible on the next scan.

Each pass collects sources sequentially. The next scan starts after the pass finishes and the poll interval expires.
Slow feeds can delay later sources. A busy collector defers the pass until the next scan.
The scheduler does not queue missed runs or repeat every interval missed while the computer was off.
After restart, it uses the stored check times. Collection stops while the backend is off or the computer sleeps.

After a failure, the scheduler waits for both the source interval and the collector cooldown to expire.
It rechecks pause state, interval, and last check time under the collector lock before each download.
Manual refreshes use the same lock and reset the automatic interval when they finish.
Source edits and manual refreshes can return `409` while an automatic download is active.

As an administrator, open **Catalogo → Dettagli e azioni** to inspect check times and collection history.
Reload the browser to see new articles and results. The frontend does not update automatically.
History uses the same statuses for automatic and manual runs and does not label their origin.
Scan failures appear in backend error logs. Completed downloads use the existing collector logs and database records.
Standard Python logging controls informational scheduler messages.

To test a shorter interval, use `PATCH /api/sources/{id}` with `{"refresh_interval_minutes":1}` in `/docs`.
Wait for the interval and a subsequent scan, then inspect `/api/sources/{id}/runs`.
A failed source can take longer because of its cooldown. Restore the desired interval after the test.
This test downloads the configured feed and writes articles to your local database.

Set `TNR_SCHEDULER_ENABLED=false` in `.env` to use manual collection only.
Set `TNR_SCHEDULER_POLL_SECONDS` to change scan frequency, not the individual source interval.
Restart the backend after configuration changes.
On normal shutdown, the worker finishes the active feed and skips remaining sources before the database closes.
An OS DNS call can delay shutdown because the HTTP timeout does not bound that call.

## Run the frontend

In a second terminal, start from the repository root:

```sh
cd frontend
npm run dev
```

Open <http://127.0.0.1:5173>. Both servers and an initialized database are required.
Vite forwards `/api` requests to the backend, so
<http://127.0.0.1:5173/api/health> returns the same health response.
Stop each server with `Ctrl+C`.

Both servers bind to loopback. Keep them local until cloud configuration and deployment checks are complete.
If a configured port is occupied, stop the conflicting process or choose a new
port explicitly. If you change the backend port, update `TNR_API_TARGET` too.

### Use the interface

For a populated prototype, keep both servers running and open a third terminal.
From the repository root:

```sh
cd backend
.venv/bin/python -m app.catalog
```

This imports the [verified catalog](sources.md) without changing existing settings.
The scheduler collects new enabled sources on a subsequent scan.
For a manual batch, disable the scheduler and restart the backend, then add `--refresh`.
That option refreshes imported enabled sources sequentially. Use `--api-url http://127.0.0.1:18000`
if the backend uses a different port. The command accepts only local HTTP API origins.
It does not use `TNR_API_TARGET`, which configures Vite separately.

Repeated imports match exact normalized feed URLs and preserve existing source settings.
Disabled sources stay disabled. Missing categories are not recreated, and new sources
use no category when the catalog slug is absent. Renamed category labels remain unchanged.
Changing a source URL breaks the catalog match. A later import can add the original URL again.
Deleted catalog sources are added again when you explicitly rerun the command.

Import operations persist individually. If import stops, fix the reported problem and rerun it.
Refresh failures do not stop other feeds. A failed refresh gives exit code 1 and remains visible in **Catalogo**.
Cooldowns also count as failed attempts. Wait before retrying. Unrelated sources are not refreshed.
The command does not start its own scheduler or download full article pages.
With the backend scheduler enabled, a manual batch can receive `409` or `429` responses.

The interface is currently in Italian. Category names are editable data and retain
their configured language. The initial category names are in English.

1. As an administrator, open **Catalogo**, then **Aggiungi fonte**.
2. Enter a name and a valid RSS/Atom URL. Select an optional category.
3. Select **Salva fonte**, then **Aggiorna** on the source card.
4. Open **Le mie fonti** and follow the source, then open **Notizie** to browse its articles.

Profiles without subscriptions first see the current catalog with enabled sources proposed.
Confirm the desired sources or select **Non ora**. Existing choices are preserved.
**Le mie fonti** changes only your subscriptions. Unfollowing a source preserves your read states.
Readers can refresh followed sources, but cannot edit the shared catalog or categories.
In Supabase mode, **Accedi con Google** starts login and **Esci** ends this browser's session.
An unapproved account sees **Accesso riservato**. Follow the [operator approval procedure](authentication.md#approve-the-administrator-and-friends).

**Notizie** combines source, category, read-status, and text filters. Submit text
search with **Cerca** or Enter. **Azzera filtri** clears all filters.
On mobile, **Filtri** expands the source, category, and read-status controls.
Its count shows active filters. Closing the panel preserves their values.
Article titles open the original page in a new tab. The read-status button stores
your choice independently of opening the article. Missing publication dates are
shown explicitly, with the acquisition time.

**Catalogo** supports source edits, category assignment, pause/reactivation, manual
refresh, and collection history. The last error stays visible until a successful
refresh clears it. A cooldown response displays the remaining wait time.
Use **Dettagli e azioni** to inspect feed URLs, check times, pause/reactivation,
history, and deletion. Editing and history appear beside the selected source.
**Categorie** supports names, identifiers, and display order. These two views are for administrators. Both deletion dialogs
explain which data is removed. Canceling a dialog does not change stored data.

The layout supports desktop and mobile widths. Labels, keyboard focus indicators,
loading/empty/error states, and retry controls are included. Unsaved forms and
filters reset when you leave a view. The browser does not poll for new articles.
Reload the page to see automatic collection results. Offline access is not available.

The editorial interface uses local Source Serif 4 and Source Sans 3 font files.
Their versions, hashes, and SIL Open Font Licenses are in `frontend/public/fonts/`.
No external font service or UI component library is required. Shared color and
spacing styles are in `frontend/src/styles.css`, with local SVG icons in `Icon.tsx`.
Browser checks cover layout at 320, 390, and 1440 pixels. This is not a full accessibility certification.

## Configuration

Copy `.env.example` to the repository root as `.env` if no private file exists.
Enable the local identity explicitly for local data access. Restart the development servers after configuration changes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TNR_APP_NAME` | `Tech News Radar` | Backend OpenAPI title |
| `TNR_DOCS_ENABLED` | `true` | Enable `/docs` and `/openapi.json` |
| `TNR_LOCAL_USER_ID` | unset | Explicit local-only identity, incompatible with `TNR_SUPABASE_URL` |
| `TNR_SUPABASE_URL` | unset | HTTPS project origin for Supabase access-token verification |
| `TNR_DATABASE_URL` | `sqlite:///data/news.db` | Database URL; relative SQLite paths start from `backend/` |
| `TNR_MIGRATION_DATABASE_URL` | unset | Optional operator connection for Alembic and access provisioning; defaults to the application URL |
| `TNR_SCHEDULER_ENABLED` | `true` | Enable automatic collection in the backend process |
| `TNR_SCHEDULER_POLL_SECONDS` | `30` | Wait between scans, range 1–300 seconds |
| `TNR_FEED_TIMEOUT_SECONDS` | `10` | Per-operation HTTP timeout, greater than 0 and at most 60 seconds |
| `TNR_FEED_MAX_BYTES` | `2000000` | Transfer and decoded-body limits, range 1024–10000000 bytes each |
| `TNR_FEED_MAX_ENTRIES` | `5000` | Entries per feed, range 1–10000 |
| `TNR_API_TARGET` | `http://127.0.0.1:8000` | Backend target for the Vite development proxy |
| `VITE_LOCAL_MODE` | unset | Explicit loopback development mode; requires the backend local identity and no Supabase settings |
| `VITE_SUPABASE_URL` | unset | Public Supabase origin, matching the backend project |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | unset | Public `sb_publishable_` key for browser authentication |

Process environment variables override `.env`. Do not store secrets in `VITE_*`
variables: Vite can include them in browser assets. Keep `.env` out of Git.
Restart Vite after changes. Production values are included at build time, so rebuild after changing them.
Invalid or incomplete frontend authentication settings show an unavailable-access screen and do not request application data.

If an older `.env` sets `TNR_FEED_MAX_ENTRIES=1000`, change it to `5000` for the starter catalog.
OpenAI's feed exceeded 1,000 entries during verification. Restart the backend after this change.

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
npm test
npm run format:check
npm run build
```

The build includes `npm run typecheck`. Frontend tests use Vitest, Testing Library,
and jsdom with mocked HTTP. Run `npm run test:watch` for interactive test development.
Run `npm run format` to format frontend source files. jsdom is pinned to a version
compatible with the supported Node 24 environment. Browser checks are still needed
for responsive layout, native dialog focus, and other behavior jsdom does not reproduce.
Backend tests use an in-process HTTP client and temporary SQLite databases initialized
through Alembic. They require no external news services and do not change the local
development database. Migration tests also check schema/model consistency and repeated upgrades.
The same database, API, collector, and scheduler tests support an optional isolated PostgreSQL run.
Use the [PostgreSQL test procedure](postgresql.md#isolated-postgresql-tests). Docker is optional and is not required for normal development.

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
