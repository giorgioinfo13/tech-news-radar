# Architecture and scope

Tech News Radar is a local application with a React frontend and a FastAPI backend.
Its backend supports shared content and personal data, with Supabase token verification or an explicit local identity adapter.
The frontend supports Google login and browser sessions. Cloud authentication setup and public deployment remain separate steps.
Simplicity and maintainability take priority over scale.

## Current foundation

- Vite serves the frontend on `127.0.0.1:5173` in development.
- Uvicorn serves FastAPI on `127.0.0.1:8000` with one worker.
- Vite proxies `/api` requests to the backend. No broad CORS policy is necessary.
- `GET /api/health` reports process health only. It does not check storage or sources.
- FastAPI exposes `/docs` and `/openapi.json` by default.
- Environment settings come from the root `.env` file or process environment.
- The frontend provides news and personal source selection, plus catalog and category management for administrators.

## Database foundation

SQLite and PostgreSQL use shared models and synchronous SQLAlchemy sessions. Alembic revision `0001` creates the
schema and eight editable categories. Schema changes are explicit migration commands,
not startup side effects. No default sources are inserted yet.

The engine enables foreign keys on every SQLite connection and uses Python's modern
transaction mode with a five-second lock timeout. Keep transactions short and use
one backend worker. Models expose timezone-aware UTC timestamps. SQLite stores naive UTC,
while PostgreSQL uses `timestamptz`. Naive Python datetime inputs are rejected.

SQLite remains the local default. PostgreSQL uses Psycopg 3, verified TLS for remote connections,
and a bounded SQLAlchemy pool with direct or session-pooler connections.
Alembic revision `0002` adapts PostgreSQL dates, collations, and long-key constraints without changing SQLite tables.
PostgreSQL tables live in the private `tnr` schema, with Data API role grants revoked.
See [PostgreSQL configuration and tests](postgresql.md) for privilege boundaries and isolated validation.
No existing data is transferred, and no Supabase configuration is applied automatically.

Revision `0004` adds a unique Supabase identity link. Operator commands approve readers or link the reserved owner.
Revision `0005` adds administrator email invitations and transactional reader creation after verified Google identity checks.
Existing profiles and revoked status take precedence. No HTTP route changes roles or assigns the owner.
See [authentication and access approval](authentication.md).

Revision `0003` adds `AppUser`, `Subscription`, and `ArticleReadState`.
It moves existing read flags to the reserved local owner and removes the global article flag.
Sources and categories belong to the catalog. Only administrators can change them.
Subscriptions and read states belong to individual users, including administrators.
See [multiuser ownership and permissions](multiuser.md) for the complete contract and migration behavior.

The initial entities are `Category`, `Source`, `Article`, and `CollectionRun`.
Each source has at most one category. Articles inherit that category. A null
category means uncategorized. Category names and slugs, and source feed URLs, are unique.

Articles preserve the original URL and publication date separately from acquisition
time. Missing publication dates stay null. Database constraints on
`(source_id, guid)` and `(source_id, url)` reject exact duplicates within a source.
SQLite uses unique constraints. PostgreSQL uses hash exclusion constraints to support long UTF-8 keys with exact comparisons.
GUIDs can be null. Different sources can reference the same article. The collector
adds conservative URL matching on top of these database constraints.

Deleting a category sets its sources' category to null and preserves their articles.
Deleting a source cascades to its articles, collection history, subscriptions, and personal read states.
Deleting a user removes only that user's subscriptions and read states. Shared content remains.
The API documents deletion behavior. The interface requires confirmation for catalog deletions.

Collection runs use `running`, `success`, `not_modified`, or `error`. A completed run
requires a finish time at or after its start. Counts must be nonnegative, and added
articles cannot exceed seen articles. The collector closes interrupted runs when
that source is next refreshed, manually or automatically.

SQL constraints enforce identity, references, and basic data consistency. The API
validates HTTP URL syntax and text limits. The downloader validates feed destinations.
The database models do not download or validate feed URLs.

## REST API

FastAPI creates one engine per application lifespan and disposes it at shutdown.
Each request uses a separate SQLAlchemy session. Write endpoints commit explicitly.
Session cleanup rolls back unfinished transactions. Startup does not wait for database access or apply migrations. The automatic worker
first accesses the database after its initial poll delay. The health endpoint remains independent of storage.
This uses FastAPI's [lifespan](https://fastapi.tiangolo.com/advanced/events/) and
[dependency cleanup](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/) patterns.

Pydantic schemas define public fields separately from database models. Routes handle
category/source changes, article queries, read status, and collection history.
Shared helpers cover sessions, bounded pagination, missing records, and constraint conflicts.
Protected routes resolve an active user on each request. No request parameter can select another user's personal data.
The default configuration denies data access. The temporary local identity adapter accepts only loopback clients and rejects bearer tokens.
It is not a login mechanism and must not be enabled behind a public proxy.
The collection service handles the separate download, parsing, and persistence workflow.

Article lists sort by publication time, or acquisition time when publication time
is absent. Descending IDs break ties. Search matches literal substrings in titles
and descriptions. Both databases use ASCII case handling, without linguistic or
semantic search. Offset pagination can shift when articles arrive between requests.
Large feeds may eventually need indexed search or cursor pagination.
Article lists default to personal subscriptions. Browsing the full shared archive is explicit and still uses the caller's own read states.

Source URLs accept HTTP/HTTPS, exclude embedded credentials and fragments, and use
Pydantic URL normalization. Saving a source does not check feed availability or
destination addresses. Only the manual refresh endpoint makes outbound requests.

Changing a feed URL clears its cache validators and current diagnostics. Existing
articles and collection history remain attached to the source. Disabling a source
preserves its articles. No collection runs are created by these API operations.

## Manual collection

`POST /api/sources/{id}/refresh` waits for the collection result. It writes a
`running` record, closes the transaction, downloads and parses the feed, then commits
new articles and the final outcome together. A failure rolls back article inserts
and records an error in a separate transaction. Storage outages can prevent that
last write. Interrupted runs are closed on the next refresh of the same source.

An application-wide lock rejects concurrent refreshes and source PATCH/DELETE requests.
It does not hold a database transaction during network access. Run exactly one backend
process/worker against the database. The lock does not coordinate separate processes
or external database edits. The scheduler uses this same collector and lock.

Refreshes have a 30-second cooldown after success. After consecutive failures, the
cooldown doubles from 60 seconds to a maximum of one hour. Rejected refreshes do not
create runs. Automatic collection also respects each source interval.

The downloader uses HTTPX, public IP checks, and at most three redirects. Each hop
connects to an already validated IP, with the original Host header and TLS hostname.
This uses HTTPX's documented [SNI extension](https://www.python-httpx.org/advanced/extensions/#sni_hostname).
Mixed public/private DNS answers, special IP ranges, nonstandard ports, and HTTPS
downgrades are rejected. Environment proxies and credentials are not used.
Only the first validated DNS address is attempted. DNS timing follows the OS resolver.

HTTP operations default to a 10-second timeout. A 30-second elapsed-time budget is
checked between download operations. It does not interrupt an active OS DNS call
or socket operation. Downloads are streamed and limited to 2 MB by default.
The client requests uncompressed content but also accepts gzip with bounded decompression.
The same size limit applies separately to transferred and decoded bytes. Invalid,
truncated, trailing, or concatenated gzip streams are rejected. Other encodings,
authentication, private networks, and nonstandard ports
are not supported in this version.

ETag and Last-Modified support conditional requests. A `304` preserves articles and
records `not_modified`. Cache headers change only after successful collection.
Validators are not forwarded across redirects or saved from redirected responses.
Configure the final feed URL to benefit from conditional requests.

Before feedparser runs, defusedxml rejects malformed XML, DTDs, entities, and excessive
nesting. See [defusedxml's controls](https://pypi.org/project/defusedxml/).
The parser receives bytes, never a URL or path. Up to 5,000 entries are accepted by
default. Titles and descriptions become plain text, capped at 1,000 and 4,000 characters.
Entries without a usable title or HTTP/HTTPS link are skipped. Missing or invalid
publication dates remain null. Atom update dates do not replace publication dates.
The original resolved article URL is stored and is never fetched by the backend.

Deduplication checks GUID first, then URL within a source. URL comparison normalizes
host/scheme/default ports and removes fragments, while preserving query parameters.
Existing articles and their read status are not overwritten. The collector loads
that source's stored GUIDs and URLs into memory. This is suitable for a small local
reader but may need indexed identity columns if article volume grows substantially.
Cross-source story clustering is outside the MVP.

Run counts include all entries seen and newly inserted articles. The difference also
includes duplicates and skipped entries. An entirely unusable nonempty feed is an error.
Collection history, source diagnostics, and logs identify failures without raw response
bodies or request URLs. There is no automatic history retention policy yet.

## Automatic collection

A single `CollectionScheduler` thread belongs to the FastAPI lifespan. It shares the
application's collector and uses Python's `threading.Event` for interruptible waits.
This periodic loop needs no APScheduler dependency or persistent job store.
See [Python event objects](https://docs.python.org/3.13/library/threading.html#event-objects)
and [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/).

After each poll delay, the worker reads enabled source IDs, ordered by oldest check time.
It closes that session before collection. `Collector.refresh_if_due` acquires the shared
lock and rereads source settings before it calls the existing collection path.
A source is due when its last check plus the greater of its interval and cooldown is reached.
Never-checked sources are due immediately. Missing, disabled, and unexpired sources are skipped.
The source interval defaults to 60 minutes. The poll delay defaults to 30 seconds.

Each pass is sequential. A busy collector defers the remaining pass. Source failures
leave other sources available, and scan failures are logged without stopping the worker.
The next pass starts after the current pass and poll delay. Missed intervals do not create jobs.
Stored check times preserve the schedule across restarts without new database fields.
Normal shutdown signals the worker, waits for its active feed, then disposes the engine.
The lifespan waits for that join outside the event loop. OS DNS resolution can delay it.

Set `TNR_SCHEDULER_ENABLED=false` to disable the worker. Change the scan delay with
`TNR_SCHEDULER_POLL_SECONDS` (1–300 seconds). Run one backend process per database.
Collection stops when the backend stops or the computer sleeps. The browser does not poll
for results. Reload it to see new articles, check times, and history.

For a sleeping backend, an opt-in GitHub Actions workflow can wake the service and request a bounded scan.
`POST /api/internal/collect` requires a dedicated secret and runs synchronously in the API thread pool, without a second collector process.
The internal timer and external-trigger mode are mutually exclusive. Both reuse the same due-source scan and guarded downloader.
External scans have a separate nonblocking scan lock, a cooldown, and per-pass limits; source operations retain their existing shared lock.
The response reports collected, failed, skipped, and deferred work. Shutdown finishes the active feed before engine disposal.
See [activation, timing, and provider limits](development.md#collection-on-render-free).

## Frontend

The interface has six hash-based views: `#news`, `#sources` (personal subscriptions), `#catalog`, `#categories`, `#invitations`, and `#proposals`.
Catalog, category, and invitation controls are visible only to administrators. The backend checks permissions independently.

Italian is the default language. The account menu also offers English before and after sign-in.
`LanguageProvider` stores `tnr-language` in browser storage, synchronizes tabs, and updates the document language.
The typed message catalog uses English keys and Italian translations without an external translation service.
Notices retain message keys and values, so an existing notice changes language without repeating its operation.
Date and number formatting use the selected locale. Language changes do not reset component state or query keys.
Articles, source and category names, and stored feed diagnostics remain unchanged.
The public privacy pages describe the language preference in both languages.
Supabase's JavaScript SDK handles Google OAuth with PKCE, session persistence, refresh, and logout.
Before loading application data, the frontend verifies access through `/api/me`. It sends the current access token on each API request.
Account changes and logout clear view state and abort previous requests. Roles come from the backend, not token metadata.
An explicit development-only local mode remains available without cloud accounts. See [authentication](authentication.md).
React state controls forms and filters. A small fetch client and query hook handle
API calls, abort obsolete requests, and retain data during refresh. No router or
server-state library is required at this size. Native form controls and `<dialog>`
provide accessible interactions without an additional component library.

The dashboard queries 20 articles per page. Search is submitted explicitly, and
filter changes reset pagination. Source/category catalogs load all API pages so
selectors do not silently omit entries beyond the first 100. Those small catalogs
stay in memory. Filtering large catalogs can be added if they grow substantially.
New readers confirm an initial selection from the shared catalog. Existing subscriptions are preserved.
The personal source view supports follow/unfollow and refresh; unfollowing leaves read states intact.

Source management supports create/edit/delete, category assignment, enable/disable,
manual refresh, last-check/error display, and paginated collection history.
Category management supports names, slugs, order, and deletion. Native confirmation
dialogs explain deletion effects and restore focus on cancellation.

Titles, descriptions, source errors, and history render as text. Article links
accept only HTTP/HTTPS without credentials and open with `noopener noreferrer`.
Opening an original article does not automatically mark it read. Read state changes
only through the explicit control. The frontend does not fetch feed URLs directly.

Filters and unsaved forms are local to the current view and reset on navigation.
There is no offline cache or interval polling. The account menu provides the UI language switch.
The web app manifest supplies a stable root identity, standalone launch mode, and standard 192/512-pixel icons.
An Apple touch icon supports Home Screen installation. The app requires a network connection and registers no service worker.
Installation adds no cache of API responses, tokens, or personal data; Supabase session persistence remains unchanged.
See [installation and device checks](development.md#install-the-web-app).
Appearance supports light, dark, and system modes through shared CSS color variables.
A small local script in the document head applies the saved preference before rendering.
The React theme provider follows system changes and synchronizes the `tnr-theme` browser preference across tabs.
Storage failures fall back to a usable in-memory choice. Theme changes do not remount the authenticated workspace or call the API.
This preference belongs to the browser, survives logout, and does not change user records.
The original branding assets remain unchanged; the full logo has a light backing in dark mode for legibility.
See the browser APIs for [system appearance](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-color-scheme)
and [storage events](https://developer.mozilla.org/en-US/docs/Web/API/Window/storage_event).
API errors provide retry guidance, including the refresh cooldown from `Retry-After`.
Vitest and Testing Library cover behavior with mocked HTTP. Browser checks cover
responsive layout and native dialog behavior separately from jsdom tests.

## Development phases

1. Repository, bilingual introduction, local development scaffold, health endpoint, and checks.
2. Database models, migrations, and basic REST endpoints.
3. RSS collection, manual refresh, and an optional verified source catalog.
4. Dashboard, source/category management, and behavioral frontend tests.
5. Scheduling, end-to-end validation, CI, and final MVP documentation.
6. Optional integrations, one separately approved task at a time.

Phases 1–4 include an optional verified source catalog and a local prototype.
The catalog CLI uses the running REST API, including its collector lock and cooldown.
It does not create a second collector, change the schema, or import sources at startup.
Automatic collection is implemented. Broader end-to-end validation and CI remain separate tasks.
Add libraries and directories when their phase needs them.
No paid API, LLM, Docker, distributed queue, or
external database service is required for the planned MVP.

Before server deployment, validate real Google login and complete cloud configuration, HTTPS, backups, and process
management in separate tasks. Loopback defaults alone are not a public deployment design.

## Source proposals

[Source proposals](source-proposals.md) add reader submissions and administrator decisions in revision `0006`.
The guide describes ownership, validation, runtime grants, tests, and the coordinated deployment sequence.
