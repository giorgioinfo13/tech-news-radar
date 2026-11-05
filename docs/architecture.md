# Architecture and scope

Tech News Radar is a local, single-user application with a React frontend and a
FastAPI backend. Simplicity and maintainability take priority over scale.

## Current foundation

- Vite serves the frontend on `127.0.0.1:5173` in development.
- Uvicorn serves FastAPI on `127.0.0.1:8000` with one worker.
- Vite proxies `/api` requests to the backend. No broad CORS policy is necessary.
- `GET /api/health` reports process health only. It does not check storage or sources.
- FastAPI exposes `/docs` and `/openapi.json` by default.
- Environment settings come from the root `.env` file or process environment.
- The frontend provides news, source management, and category management views.

## Database foundation

SQLite uses synchronous SQLAlchemy sessions. Alembic revision `0001` creates the
schema and eight editable categories. Schema changes are explicit migration commands,
not startup side effects. No default sources are inserted yet.

The engine enables foreign keys on every SQLite connection and uses Python's modern
transaction mode with a five-second lock timeout. Keep transactions short and use
one backend worker. Models expose timezone-aware UTC timestamps. SQL stores UTC
without timezone metadata; naive Python datetime inputs are rejected.

The schema uses portable SQL types and constraints. PostgreSQL remains a possible
future migration, not a current dependency or a tested replacement. Driver setup,
URL/index limits, and migration behavior need validation before a switch.

The initial entities are `Category`, `Source`, `Article`, and `CollectionRun`.
Each source has at most one category. Articles inherit that category. A null
category means uncategorized. Category names and slugs, and source feed URLs, are unique.

Articles preserve the original URL and publication date separately from acquisition
time. Missing publication dates stay null. Composite unique constraints on
`(source_id, guid)` and `(source_id, url)` reject exact duplicates within a source.
GUIDs can be null. Different sources can reference the same article. The collector
adds conservative URL matching on top of these database constraints.

Deleting a category sets its sources' category to null and preserves their articles.
Deleting a source cascades to its articles and collection history. The API documents
this behavior. The future UI must require confirmation before deletion.

Collection runs use `running`, `success`, `not_modified`, or `error`. A completed run
requires a finish time at or after its start. Counts must be nonnegative, and added
articles cannot exceed seen articles. The collector closes interrupted runs when
that source is next refreshed. No scheduler is implemented yet.

SQL constraints enforce identity, references, and basic data consistency. The API
validates HTTP URL syntax and text limits. The downloader validates feed destinations.
The database models do not download or validate feed URLs.

## REST API

FastAPI creates one engine per application lifespan and disposes it at shutdown.
Each request uses a separate SQLAlchemy session. Write endpoints commit explicitly.
Session cleanup rolls back unfinished transactions. Startup does not connect to
the database or apply migrations. The health endpoint remains independent of storage.
This uses FastAPI's [lifespan](https://fastapi.tiangolo.com/advanced/events/) and
[dependency cleanup](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/) patterns.

Pydantic schemas define public fields separately from database models. Routes handle
category/source changes, article queries, read status, and collection history.
Shared helpers cover sessions, bounded pagination, missing records, and constraint conflicts.
The collection service handles the separate download, parsing, and persistence workflow.

Article lists sort by publication time, or acquisition time when publication time
is absent. Descending IDs break ties. Search matches literal substrings in titles
and descriptions. SQLite case handling is primarily ASCII, without linguistic or
semantic search. Offset pagination can shift when articles arrive between requests.
Large feeds may eventually need indexed search or cursor pagination.

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
or external database edits. A future scheduler must use the same collector entry point.

Refreshes have a 30-second cooldown after success. After consecutive failures, the
cooldown doubles from 60 seconds to a maximum of one hour. Rejected refreshes do not
create runs. Source intervals remain settings for the future scheduler.

The downloader uses HTTPX, public IP checks, and at most three redirects. Each hop
connects to an already validated IP, with the original Host header and TLS hostname.
This uses HTTPX's documented [SNI extension](https://www.python-httpx.org/advanced/extensions/#sni_hostname).
Mixed public/private DNS answers, special IP ranges, nonstandard ports, and HTTPS
downgrades are rejected. Environment proxies and credentials are not used.
Only the first validated DNS address is attempted. DNS timing follows the OS resolver.

HTTP operations default to a 10-second timeout. A 30-second elapsed-time budget is
checked between download operations. It does not interrupt an active OS DNS call
or socket operation. Downloads are streamed and limited to 2 MB by default.
The client requests uncompressed content and rejects unsolicited compression.
Feeds that require compression, authentication, private networks, or nonstandard ports
are not supported in this version.

ETag and Last-Modified support conditional requests. A `304` preserves articles and
records `not_modified`. Cache headers change only after successful collection.
Validators are not forwarded across redirects or saved from redirected responses.
Configure the final feed URL to benefit from conditional requests.

Before feedparser runs, defusedxml rejects malformed XML, DTDs, entities, and excessive
nesting. See [defusedxml's controls](https://pypi.org/project/defusedxml/).
The parser receives bytes, never a URL or path. Up to 1,000 entries are accepted by
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

## Planned MVP

Use APScheduler in the backend lifecycle. Manual and scheduled refreshes must
share the collector's overlap protection, request limits, and retry behavior.
Collection stops when the backend stops or the computer sleeps.

## Frontend

The Italian interface has three hash-based views: `#news`, `#sources`, and `#categories`.
React state controls forms and filters. A small fetch client and query hook handle
API calls, abort obsolete requests, and retain data during refresh. No router or
server-state library is required at this size. Native form controls and `<dialog>`
provide accessible interactions without an additional component library.

The dashboard queries 20 articles per page. Search is submitted explicitly, and
filter changes reset pagination. Source/category catalogs load all API pages so
selectors do not silently omit entries beyond the first 100. Those small catalogs
stay in memory. Filtering large catalogs can be added if they grow substantially.

Source management supports create/edit/delete, category assignment, enable/disable,
manual refresh, last-check/error display, and paginated collection history.
Category management supports names, slugs, order, and deletion. Native confirmation
dialogs explain deletion effects and restore focus on cancellation.

Titles, descriptions, source errors, and history render as text. Article links
accept only HTTP/HTTPS without credentials and open with `noopener noreferrer`.
Opening an original article does not automatically mark it read. Read state changes
only through the explicit control. The frontend does not fetch feed URLs directly.

Filters and unsaved forms are local to the current view and reset on navigation.
There is no offline cache, polling, dark mode, or UI language switch yet.
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

Phases 1–4 are implemented, except for the optional verified source catalog.
Scheduling, integration validation, and CI are the next separately approved phase.
Add libraries and directories when their phase needs them.
No paid API, LLM, Docker, distributed queue, or
external database service is required for the planned MVP.

Before server deployment, design authentication, HTTPS, backups, and process
management in a separate task. Loopback defaults alone are not a public deployment design.
