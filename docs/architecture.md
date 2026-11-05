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
- The frontend contains a static introduction, not a news dashboard.

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
GUIDs can be null. Different sources can reference the same article. URL normalization
and GUID-first matching belong to the future collector, not the database models.

Deleting a category sets its sources' category to null and preserves their articles.
Deleting a source cascades to its articles and collection history. The future API
and UI must expose this deletion behavior clearly.

Collection runs use `running`, `success`, `not_modified`, or `error`. A completed run
requires a finish time at or after its start. Counts must be nonnegative, and added
articles cannot exceed seen articles. These constraints do not implement a scheduler
or recover interrupted runs; the collection service will handle those behaviors.

SQL constraints enforce identity, references, and basic data consistency. HTTP URL
validation, text limits, and feed access protections belong to the future API and
collector. The database models do not download or validate feed URLs.

## Planned MVP

Add Pydantic schemas and management endpoints on top of the persistence layer.

Separate HTTP download, RSS/Atom parsing, normalization, and persistence through
small modules and functions. Use `httpx` and `feedparser`. Deduplicate within each
source using GUID and URL, with database constraints. Cross-source story clustering
is outside the MVP.

Use APScheduler in the backend lifecycle. Manual and scheduled refreshes must
share overlap protection. Use one backend worker, request timeouts, response-size
limits, conditional HTTP requests, and backoff. Record recent collection outcomes.
Collection stops when the backend stops or the computer sleeps.

The dashboard will support chronological articles, source/category filters,
basic text search, and read/unread status. A separate page will manage sources,
categories, refresh actions, and collection errors. Render descriptions as plain text.

Validate feed destinations, DNS results, and redirect targets before requests.
Reject private-network destinations and unsafe URL schemes. Validate original
article links before display. Do not fetch full articles or run feed content as code.

## Development phases

1. Repository, bilingual introduction, local development scaffold, health endpoint, and checks.
2. Database models, migrations, and basic REST endpoints.
3. RSS collection, manual refresh, and an optional verified source catalog.
4. Dashboard, source/category management, and behavioral frontend tests.
5. Scheduling, end-to-end validation, CI, and final MVP documentation.
6. Optional integrations, one separately approved task at a time.

Phase 1 and the database foundation of phase 2 are implemented. Management APIs
are the next separately approved step. Add libraries and directories when their
phase needs them. shadcn/ui, routing, and server-state utilities can enter
with the interactive frontend. No paid API, LLM, Docker, distributed queue, or
external database service is required for the planned MVP.

Before server deployment, design authentication, HTTPS, backups, and process
management in a separate task. Loopback defaults alone are not a public deployment design.
