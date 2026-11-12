# Local development

Run all commands from the repository root unless a step changes the directory.
The current scaffold requires Python 3.13, Node.js 24, npm, and access to the
Supabase project. Version hints are in `.python-version` and `.nvmrc`. Docker is
required only for the isolated local PostgreSQL test service.

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

## Configure the database

Fill the private root `.env` with the Supabase session-pooler URL for `tnr_app`,
verified TLS settings, authentication origin, and public frontend settings. The
database URL is required; no file-backed or embedded database is supported.

The production schema is migrated only by the authorized release workflow. For
an explicitly authorized operator check from the repository root:

```sh
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic check
```

The expected revision is
`0012 (head)`, with no pending schema changes. Revision `0012` adds the latest app access check. Revision `0011` adds a separate article discussion URL. Revision `0010` persists RSS attempt times before downloads. Revision `0003` adds personal subscriptions and read states.
It preserves existing sources, categories, articles, and collection history. Existing read flags belong only to the reserved local owner.
Revision `0004` adds explicit Supabase identity links without changing existing profiles or personal data.
Revision `0005` adds administrator email invitations. It preserves existing profiles, subscriptions, and read states.

Run `alembic upgrade head` after updates that add migrations. Repeating it on an
up-to-date database preserves category edits and existing data. The API does not
create tables or apply migrations at startup.

Before deploying the article discussion-link change, apply revision `0011` with the existing migration command.
It removes the `Comments` placeholder from articles associated with the standard Hacker News feed.
The next normal collection requests the full feed and restores discussion links for matching articles.
Older articles absent from the feed cannot recover their lost discussion link.
Other descriptions remain unchanged. Downgrading removes the new column but does not restore the removed placeholder.

`TNR_DATABASE_URL` must identify Supabase PostgreSQL through a direct connection
or the session pooler on port 5432. Remote connections require `sslmode=verify-full`
and an absolute `sslrootcert` path. See [PostgreSQL setup and isolated tests](deployment.md#postgresql-configuration)
for TLS, schema isolation, and migration credentials.

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

Local development uses the configured Supabase project and Google login.
Without Supabase configuration, data endpoints return `401`. Health and API
documentation remain available. See the [authentication configuration](authentication.md).
See [multiuser behavior](authentication.md#user-roles-and-personal-data) for roles and migration details.

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

Use `/docs` to inspect request schemas and try the endpoints against the configured Supabase database.
These operations change persistent data. The local identity adapter is for loopback development only.
The backend requires an active application user and checks permissions on each request.
Only administrators can create, edit, or delete categories and sources.

| Method | Path | Behavior |
| --- | --- | --- |
| `GET`, `POST` | `/api/categories` | List or create categories |
| `PATCH`, `DELETE` | `/api/categories/{id}` | Edit or delete a category |
| `GET`, `POST` | `/api/sources` | List or create source configurations |
| `PATCH`, `DELETE` | `/api/sources/{id}` | Edit or delete a source |
| `POST` | `/api/sources/{id}/refresh` | Collect an enabled, authorized source within shared limits |
| `POST` | `/api/sources/refresh` | Collect eligible authorized sources and return aggregate counts |
| `GET` | `/api/sources/{id}/runs` | List a source's collection history |
| `GET` | `/api/articles` | List, filter, and search articles |
| `PATCH` | `/api/articles/{id}` | Set read/unread status |
| `GET` | `/api/me` | Read the current user's identity and role |
| `GET` | `/api/subscriptions` | List the current user's followed sources |
| `PUT`, `DELETE` | `/api/subscriptions` | Follow the full catalog or remove all current-user subscriptions; return `changed` count |
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
for a literal substring. ASCII letters match without case sensitivity in PostgreSQL.
Non-ASCII case variants remain distinct. `%` and `_` are literal characters.
An empty or whitespace-only search applies no text filter. Categories in article responses
reflect the source's current category. Disabled sources' existing articles remain visible.

Create a category with `{"name":"Custom","slug":"custom","sort_order":0}`.
Slugs use lowercase ASCII letters, digits, and single hyphens between groups.
Create a source with `{"name":"Example","feed_url":"https://example.org/feed.xml"}`.
This is a placeholder URL, not a verified feed. Optional source fields are `category_id`,
`enabled` (default `true`), and `refresh_interval_minutes` (default 60, range 1–10080).
The scheduler uses the greater of this interval, 15 minutes, and error backoff after the latest attempt or completed check.
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
Changing a source URL preserves history and rate limits but clears cache validators and current errors.
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

Wait at least 15 minutes after the latest attempt or completed check of the same source.
All users, single-source buttons, news refreshes, and scheduled scans share this limit.
Error backoff is `max(900, min(3600, 30 × 2^min(failures, 7)))` seconds.
An attempt increments the failure counter before network access. Success resets it to zero.
Interrupted attempts therefore retain their timestamp and backoff after restart.
Refresh does not wait or queue another job when the collector is busy. Source edits and deletions also return `409`
during collection. Creating sources and reading articles remain available.

Only public HTTP/HTTPS destinations on ports 80/443 are supported. The collector checks
DNS answers and redirects, verifies TLS certificates, and ignores environment proxies.
It requests uncompressed content and also accepts gzip within the same decoded-size limit.
Other compression formats and concatenated gzip streams are rejected.
Malformed XML, DTDs, entities, excessive nesting, and oversized feeds are rejected.
An absolute timeout cancels HTTP work, including slow headers and bodies. DNS waiting is bounded separately.
See [collection architecture](architecture.md#manual-collection) for limits and tradeoffs.

Sources are not installed automatically. The optional catalog command below imports verified feeds.
New sources are not followed automatically. Select them in **Le mie fonti**, or use `PUT /api/subscriptions/{source_id}` in `/docs`.
Existing sources are followed once for the local owner during migration `0003`.
Automatic collection uses the same guarded collector and history as manual refresh.
The news refresh requires revision `0010`. Apply it during a separately authorized release.

### Refresh from News

Select **Aggiorna fonti** in **Notizie**. On touch devices, pull down at least 90 pixels from the top and release.
The button also works with a keyboard. The gesture excludes controls, links, multiple touches, horizontal movement, and the screen edges.
Opening or returning to News never starts collection. Both actions send one authenticated `POST /api/sources/refresh`.
Administrators can check all enabled catalog sources. Readers can check only followed sources.
The backend rechecks active access and subscriptions before each download. Browser filters do not select the collection scope.

A manual request can advance a source's configured schedule after the shared 15-minute minimum and error backoff expire.
Scheduled collection also waits for the configured interval. Every completed manual check restarts that interval, including HTTP 304.
Never-attempted sources come first, followed by the oldest attempts. A recent source does not block other eligible sources.
No global manual cooldown postpones untouched sources.

Each news request attempts at most **10 sources** with a **45-second collection budget**.
The downloader receives the remaining budget. Each feed has an absolute HTTP deadline of `min(30, 3 × TNR_FEED_TIMEOUT_SECONDS)` seconds.
Individual network and DNS waits are capped at `min(10, TNR_FEED_TIMEOUT_SECONDS)` seconds.
Parsing and database commits add local processing time. These budgets are not a guaranteed end-to-end response deadline during process suspension or database outages.
DNS runs in one short-lived child process, without inherited environment variables or application imports.
A timeout terminates and reaps that child before the next feed. A stuck hostname therefore cannot block other sources or accumulate workers.

The result contains `checked`, `added`, `failed`, `skipped`, `deferred`, and optional `retry_after` counts/seconds.
`checked` includes failed attempts. `skipped` includes disabled, recent, and backoff sources within the authorized scope.
`deferred` counts eligible sources left by the operation limits. The UI reports partial results and does not retry automatically.
After each request, including cooldowns and errors, the UI reloads articles from the database with the current filters and read states.
It disables repeated input while a request runs and for three seconds afterward. A disconnected response has an unconfirmed outcome, never a success notice.
An active backend request can finish after the browser disconnects. Persistent limits prevent a repeated download.

Conditional requests use saved ETag and Last-Modified values. HTTP 304 adds no articles.
A server without conditional support can send the full feed. Existing GUID/URL deduplication then discards already stored articles.
Article pages are never fetched. This path never calls Gemini or changes AI budgets, digest schedules, or retention.

A shared nonblocking gate coordinates all collector instances and source changes.
PostgreSQL uses a session advisory lock on one connection, with no open transaction during HTTP.
PostgreSQL advisory locks release automatically when their owning connection closes.
Suspension retains a live lock. An HTTP deadline is checked when execution resumes. Keep the supported one-process, one-worker deployment.

## Automatic collection

Apply migrations before you start the backend. Use one process and one worker per database.
The scheduler starts with the backend and waits 30 seconds before its first scan.
It checks enabled sources, with never-checked and older sources first.
Each source has a default interval of 60 minutes, measured from its latest attempt or completed check, subject to the shared minimum and backoff.
New enabled sources become eligible on the next scan.

Each pass attempts at most 25 sources sequentially, with a 240-second budget checked between feeds. The next scan starts after the pass finishes and the poll interval expires.
Slow feeds can delay later sources. A busy collector defers the pass until the next scan.
The scheduler does not queue missed runs or repeat every interval missed while the computer was off.
After restart, it uses the stored check times. Collection stops while the backend is off or the computer sleeps.

After a failure, the scheduler waits for both the source interval and the collector cooldown to expire.
It rechecks pause state, interval, and last check time under the collector lock before each download.
Manual refreshes use the same lock and reset the automatic interval when they finish.
Source edits and manual refreshes can return `409` while an automatic download is active.

As an administrator, open **Catalogo → Dettagli e azioni** to inspect check times and collection history.
Use **Aggiorna fonti** in **Notizie** to collect eligible feeds and reload articles. The frontend does not poll automatically.
History uses the same statuses for automatic and manual runs and does not label their origin.
Scan failures appear in backend error logs. Completed downloads use the existing collector logs and database records.
Standard Python logging controls informational scheduler messages.

To test a shorter interval, use `PATCH /api/sources/{id}` with `{"refresh_interval_minutes":1}` in `/docs`.
Wait for the shared 15-minute minimum and a subsequent scan, then inspect `/api/sources/{id}/runs`.
A failed source can take longer because of its cooldown. Restore the desired interval after the test.
This test downloads the configured feed and writes articles to the configured Supabase database.

Set `TNR_SCHEDULER_ENABLED=false` in `.env` to disable the internal timer.
Without an external trigger secret, this leaves manual collection only.
Set `TNR_SCHEDULER_POLL_SECONDS` to change scan frequency, not the individual source interval.
Restart the backend after configuration changes.
On normal shutdown, the worker finishes the active feed and skips remaining sources before the database closes.
The downloader bounds HTTP work and DNS waiting. A timed-out DNS child is terminated before the next feed.

### Collection on Render Free

The prepared workflow `.github/workflows/collect.yml` requests one scan at minute 17 of each hour (UTC).
It remains inactive unless the repository variable `TNR_COLLECTION_ENABLED` is exactly `true`.
It runs only on `main` in the original repository, with read-only repository permission and one concurrent job.
The runner executes the standard-library script `scripts/trigger_collection.py`. It does not connect to the database or download feeds.

The script first requests `/api/health` without credentials, with up to 12 attempts for cold starts.
It then sends one `POST /api/internal/collect`, with a dedicated bearer secret and a 600-second response timeout.
It accepts only HTTPS `*.onrender.com` origins and refuses redirects. No credential appears in the URL.
A POST timeout leaves completion unknown; the script does not repeat the POST.

The backend reuses the existing collector, downloader, persisted due times, and source lock.
Each scan permits up to 25 feed attempts and checks a 240-second budget between feeds.
An active feed finishes within its own network budget. Parsing and database work can extend the scan budget.
Scans cannot overlap. A 300-second cooldown follows every scan, including empty or failed scans.
This scan cooldown resets on restart; persisted source intervals and backoff do not.
No new timer thread runs in external-trigger mode. One backend process per database remains mandatory.

Hourly triggers do not guarantee hourly feed updates. A source's interval starts when its previous check finishes.
A 60-minute interval can therefore defer a feed until the following hourly trigger, giving approximately two hours between checks.
Missed schedules create no backlog. Remaining sources wait for the next scan, with unchecked and oldest sources first.

After an explicitly authorized deployment with PostgreSQL, configure these values:

| Destination | Setting | Value and type |
| --- | --- | --- |
| Render environment | `TNR_SCHEDULER_ENABLED` | `false`, public setting |
| Render environment | `TNR_COLLECTION_TRIGGER_SECRET` | Private random URL-safe secret, 32–128 characters |
| GitHub Actions repository secret | `TNR_COLLECTION_TRIGGER_SECRET` | Same secret as Render; not a Supabase key |
| GitHub Actions repository variable | `TNR_BACKEND_URL` | Actual `https://SERVICE.onrender.com` origin, public |
| GitHub Actions repository variable | `TNR_COLLECTION_ENABLED` | `true` only after the other values are verified |

Generate the secret privately with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` when configuration is authorized.
Do not put it in Git, frontend variables, screenshots, or logs. Leave local `.env` unchanged for internal scheduling.
The backend rejects configuration that enables both the internal timer and the external trigger.

After activation, run **Actions → Collect feeds → Run workflow** on `main`.
Check the result counts and the administrator's collection history. Repeat after at least 20 minutes without application traffic to test cold start.
HTTP `409`/`429` means deferred work, not completed collection. Partial scans or feed errors fail the workflow for operator attention.
Check Actions for failures and disabled schedules. To stop requests, set `TNR_COLLECTION_ENABLED=false`.
To revoke the trigger credential, remove or replace it on Render and update GitHub before reactivation.

Provider limits, checked on 2026-11-06:

- [Render Free](https://render.com/docs/free) sleeps after 15 idle minutes and takes about one minute to wake.
  Its filesystem is ephemeral; remote PostgreSQL is required before this deployment. Workspaces share 750 free instance hours monthly.
  Bandwidth limits and high outbound traffic can suspend service. This workflow performs collection, not continuous keep-alive requests.
- [Render cron jobs](https://render.com/docs/cronjobs) cost at least $1 monthly per job, so they are not the free default.
- [GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
  can be delayed or dropped, and public-repository schedules stop after 60 days without repository activity.
  Re-enable the workflow through Actions when necessary; this is not a guaranteed-time scheduler.
  [Standard hosted runners are free for public repositories](https://docs.github.com/en/actions/concepts/billing-and-usage).

Local tests use temporary migrated databases and mocked feeds and HTTP responses.
Render suspension, actual GitHub execution, and collection against remote PostgreSQL remain deployment checks.

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

### Install the web app

The manifest supplies the app name, icons, root launch URL, and standalone display mode.
The app requires a network connection. It has no service worker or application-managed offline cache.
Installation does not change access approval or the Supabase session stored by the SDK.

For phone tests, use an approved HTTPS deployment with working API routing and OAuth return URLs.
`127.0.0.1` on a phone refers to the phone, not the development computer.
Keep the development servers on loopback. Desktop Chrome can test installation from the local frontend URL.

- **iPhone, Safari:** open the app URL, then select **Share → Add to Home Screen**.
  Enable **Open as Web App** if available, then select **Add**.
- **Android, Chrome:** open the app URL, then select **⋮ → Install and create shortcut → Install**.
  Menu labels can differ by browser version.

Launch from the new icon. Check the name, icon, and absence of the browser address bar.
Check light, dark, and system appearance. The manifest supplies a light launch background;
the page updates its theme color after launch.
Icons use `purpose: any`: their artwork extends beyond the safe area for maskable icons.
The supplied PNGs retain transparent corners. Check the icon background and cropping on each phone before release.

Start Google login from the installed app. Complete the [installed-session checks](authentication.md#installed-web-app-sessions)
before accepting mobile support. A desktop test or mobile viewport does not validate this flow on a phone.

Reload the app to load a new frontend build. Hosting must revalidate HTML and the manifest after deployment.
No service-worker activation or cache reset is required.
Name and icon changes follow the browser's update schedule and can require reinstallation.
Do not reinstall during an OAuth redirect: removal can discard the pending session and PKCE verifier.
Offline use is unsupported; the browser can show its network error page.

Local Chrome on macOS passed installation, standalone launch, light/dark appearance, Google login, logout, and session recovery after reopening.
Phone installation, icon rendering, OAuth, and installed-app token renewal remain unverified. No HTTPS deployment is configured for these checks yet.

References: [Apple installation guide](https://support.apple.com/guide/iphone/iphea86e5236/ios),
[Chrome Android installation](https://support.google.com/chrome/answer/9658361?co=GENIE.Platform%3DAndroid&hl=en),
[Chrome installation criteria](https://developer.chrome.com/blog/update-install-criteria),
and [maskable icon safe area](https://web.dev/articles/maskable-icon).

### Use the interface

For a populated prototype, keep both servers running and open a third terminal.
From the repository root:

```sh
cd backend
.venv/bin/python -m app.catalog
```

This imports the [verified catalog](architecture.md#starter-sources) without changing existing settings.
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

The interface defaults to Italian, regardless of the browser language. The instructions below use the Italian labels.
Open the top-right menu and select **Lingua → English** to use English.
The menu then shows **Language**, with **Italiano** and **English** as its options.
Article content, source names, category names, and stored feed diagnostics retain their original language.

The browser stores the preference as `tnr-language` and synchronizes it between tabs.
It is not an account setting and is not sent to the API. Sign-out preserves the preference.
If storage is blocked, the choice lasts until the page is reloaded.
An unknown or removed preference selects Italian. Browser and installed-app storage can be separate.
Changing language preserves filters, form input, subscriptions, and read states. It does not repeat API requests.
Labels, notices, date formats, and the document language update together.
The privacy link opens `/privacy.html` in Italian or `/privacy.en.html` in English. Both pages are public.

1. As an administrator, open **Catalogo**, then **Aggiungi fonte**.
2. Enter a name and a valid RSS/Atom URL. Select an optional category.
3. Select **Salva fonte**, then **Aggiorna** on the source card.
4. Open **Le mie fonti** and follow the source, then open **Notizie** to browse its articles.

Profiles without subscriptions first see the current catalog with enabled sources proposed.
Confirm the desired sources or select **Non ora**. Existing choices are preserved.
**Le mie fonti** changes only your subscriptions. Unfollowing a source preserves your read states.
**Segui tutte** follows the entire current catalog, including sources with paused collection.
**Non seguire più nessuna** asks for confirmation, then removes all your subscriptions.
Both actions work for readers and administrators. Each uses one request and one database transaction.
Neither action downloads feeds, changes other users' choices, or subscribes you to future catalog additions.
The initial source chooser has **Seleziona tutte** and **Deseleziona tutte** controls. They change the selection before saving.
Controls stay disabled during saving and subscription reload. After a lost response, the page reloads subscriptions without retrying the write.
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
Use **Aggiorna fonti** in **Notizie** to reload articles and check eligible sources. Offline access is not available.

Open the top-right menu and use **Tema** to select **Sistema**, **Chiaro**, or **Scuro**.
The default is **Sistema**, which follows operating-system changes while the page is open.
The choice is stored in this browser and synchronized between tabs. It is not an account setting and is not sent to the API.
Logout preserves it. If browser storage is blocked, the choice lasts until the page is reloaded.
Changing the theme preserves filters, unsaved forms, subscriptions, and read states.

For a browser check, change the system appearance, select an explicit theme, then reload.
Also check keyboard selection, mobile layout, form controls, notices, and confirmation dialogs in both themes.

The editorial interface uses local Source Serif 4 and Source Sans 3 font files.
Their versions, hashes, and SIL Open Font Licenses are in `frontend/public/fonts/`.
No external font service or UI component library is required. Shared color and
spacing styles are in `frontend/src/styles.css`, with local SVG icons in `Icon.tsx`.
Browser checks cover layout at 320, 390, and 1440 pixels. This is not a full accessibility certification.

## Configuration

Copy `.env.example` to the repository root as `.env` if no private file exists.
Configure the Supabase database and authentication values before starting the backend.
Restart the development servers after configuration changes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TNR_APP_NAME` | `Tech News Radar` | Backend OpenAPI title |
| `TNR_ENVIRONMENT` | `development` | `production` requires Supabase, PostgreSQL with verified TLS and `tnr_app`, and disabled API docs |
| `TNR_DOCS_ENABLED` | `true` | Enable `/docs` and `/openapi.json` |
| `TNR_LOCAL_USER_ID` | unset | Explicit local-only identity, incompatible with `TNR_SUPABASE_URL` |
| `TNR_SUPABASE_URL` | unset | HTTPS project origin for Supabase access-token verification |
| `TNR_DATABASE_URL` | required | Supabase PostgreSQL application URL with verified TLS |
| `TNR_MIGRATION_DATABASE_URL` | unset | Optional operator connection for Alembic and access provisioning; defaults to the application URL |
| `TNR_SCHEDULER_ENABLED` | `true` | Enable automatic collection in the backend process |
| `TNR_SCHEDULER_POLL_SECONDS` | `30` | Wait between scans, range 1–300 seconds |
| `TNR_COLLECTION_TRIGGER_SECRET` | unset | Private bearer secret for bounded external scans; requires internal scheduler disabled |
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

Each push to `main` runs **CI checks** for the backend and frontend, without production credentials or deployment.
The manual **Release frontend only** and **Release full** workflows repeat their required checks before publication.
See [checks and manual releases](deployment.md#checks-and-manual-releases-from-main) for workflow installation, token limitations, and release selection.

Backend, from `backend/`:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pip check
```

Frontend, from `frontend/`:

The frontend separates application code, automated checks, and deployment files:

- `src/`: application code, including the interactive welcome and loading screens.
- `tests/`: automated regression tests and test helpers. Keep these checks after a release.
- `dist/`: production files generated by `npm run build`. Publish this directory to the frontend host.

Test files verify application behavior. Their presence does not mark a feature as experimental or prevent a production release.
The production bundle does not include the test suite. TypeScript checks both application code and tests before the build.

```sh
npm run lint
npm test
npm run format:check
npm run build
```

The build includes `npm run typecheck`. Frontend tests use Vitest, Testing Library,
and jsdom with mocked HTTP. Run `npm run test:watch` for interactive test development.
Run `npm run format` to format frontend source files and tests. jsdom is pinned to a version
compatible with the supported Node 24 environment. Browser checks are still needed
for responsive layout, native dialog focus, and other behavior jsdom does not reproduce.
Backend tests use an in-process HTTP client and disposable local PostgreSQL databases
initialized through Alembic. They require no external news services and never connect
to Supabase. Migration tests also check schema/model consistency and repeated upgrades.
Use the [PostgreSQL test procedure](development.md#isolated-postgresql-tests).

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

Do not commit credentials, environment files, generated assets,
or virtual environments. Preserve the project's [MIT License](../LICENSE) and any
applicable third-party notices.

## Source proposals

See [source proposal behavior and API](architecture.md#source-proposals) and
[publication and grants](deployment.md#source-proposal-rollout).

## Shared AI briefs — local implementation

[AI briefs](ai-briefs.md) require local revision `0009` and remain disabled by default.
Activation also requires `TNR_AI_BUDGET_RISK_ACCEPTED=true`, which accepts a prudential reservation policy, not a guaranteed provider invoice cap.
Never use the Supabase database for a test. Use the suite's disposable local PostgreSQL databases.
Run `.venv/bin/pytest tests/test_ai_gemini.py tests/test_ai_briefs.py tests/test_ai_digest.py tests/test_ai_diagnostics.py tests/test_digest_trigger_client.py` from `backend/`.
Run `npm test -- tests/briefs.test.tsx` from `frontend/`.
Gemini counting and generation use simulated HTTP. The test fixture forbids real HTTP and disables personal dotenv loading.
No key is required. The [loopback-only PostgreSQL fixture](development.md#isolated-postgresql-tests) verifies the transactions.
The old Xing/OpenRouter runtime, trial CLI commands, and tokenizer assets have been removed.
The BYOK adapter and its tests are removed. Direct Gemini counting and HTTP responses remain simulated in tests.
Do not reuse historical trial directories or markers.
See [token evidence and activation blockers](ai-briefs.md#token-and-provider-contract) before any future live test.

Agent work logs and investigation records belong in local `docs/agent-notes/`, excluded through `.gitignore`.
Shared requirements and operating instructions remain in tracked guides. Do not link tracked guides to local notes.

## Local authentication

The backend denies data requests unless Supabase authentication or local identity is configured. Health and optional API documentation remain available.
The application database remains Supabase PostgreSQL in every application mode.
For a loopback-only identity adapter, set these values in the private root `.env`:

```dotenv
TNR_LOCAL_USER_ID=00000000-0000-0000-0000-000000000001
VITE_LOCAL_MODE=true
```

Omit Supabase authentication settings and restart both servers on `127.0.0.1`.
`TNR_DATABASE_URL` must still point to Supabase PostgreSQL. All local requests then use this one application profile.
The frontend local mode is disabled in production builds.
This setting is a development identity adapter, not a password or login mechanism.
It rejects non-loopback clients and bearer tokens. It never reads user-selection headers or query parameters.
A public proxy can make remote requests appear local, so never enable this adapter on Render or behind a public proxy.
Do not run multiple backend instances to simulate different users against the same database.

The frontend offers personal source selection, read states, and role-aware controls.
Google login and session management require the [Supabase configuration](authentication.md).
For direct subscription tests, use the local `/docs` interface:

1. Call `GET /api/me` to inspect the selected profile.
2. Call `GET /api/sources` to inspect the shared catalog.
3. Call `PUT /api/subscriptions/{source_id}` to follow a source. No body is required.
4. Call `GET /api/articles` to inspect followed sources with your own read states.
5. Call `PATCH /api/articles/{article_id}` with `{"is_read":true}` or `{"is_read":false}`.
6. Call `DELETE /api/subscriptions/{source_id}` to unfollow the source without deleting read states.

`GET /api/subscriptions` returns only the current user's subscriptions, with the standard pagination envelope.
PUT and DELETE return `204` and are idempotent. A subscription PUT for a missing source returns `404`.
Missing local identity returns `401`. Unknown, inactive, or unauthorized users receive `403`.
Neither subscriptions nor article updates accept a target user ID.

## Isolated PostgreSQL tests

All backend tests use disposable local PostgreSQL databases initialized through real Alembic migrations.
The fixture requires a literal loopback address and refuses remote hosts, including Supabase hosts.
It creates a unique `tnr_test_*` database for each database test and drops only that generated database afterward.
The supplied database is used only to create and drop test databases. Use a local test role with `CREATEDB`.
Never forward the test port to a personal or remote database.

With an existing disposable PostgreSQL server, set `TNR_TEST_POSTGRES_URL` to its administrative connection URL.
This variable is not read from `.env` and has no application effect.
Run from the repository root:

```sh
TNR_TEST_POSTGRES_URL='postgresql+psycopg://postgres:tnr-local-test-only@127.0.0.1:55439/postgres?sslmode=disable' \
  backend/.venv/bin/pytest backend/tests
```

Docker is an optional way to supply that server. These commands use a disposable container without a persistent volume:

If Docker Desktop is installed but stopped, start it with `docker desktop start` before these commands.

```sh
docker run --detach --rm --name tnr-postgres-check \
  --publish 127.0.0.1:55439:5432 \
  --env POSTGRES_PASSWORD=tnr-local-test-only postgres:17
docker exec tnr-postgres-check pg_isready -U postgres
docker exec tnr-postgres-check psql -U postgres -c \
  'CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;'
```

Wait for `pg_isready` to report success before creating the test roles and running pytest.
The three roles exercise the migration's Data API privilege revocations. They exist only in the disposable cluster.
After the tests, remove the container:

```sh
docker stop tnr-postgres-check
```

The PostgreSQL suite tests real migrations, schema/model comparison, constraints, Unicode keys, search, ordering, APIs, collection, and scheduler behavior.
HTTP downloads remain mocked. Offline SQL generation and connection-policy tests run without a PostgreSQL server.
Local PostgreSQL tests do not verify Supabase pooler connectivity, certificates, hosted role inheritance, or Data API settings.
Those checks require a later authorized remote validation.
