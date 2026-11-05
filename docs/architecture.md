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

## Planned MVP

Use SQLite with synchronous SQLAlchemy sessions and Pydantic API schemas.
Add Alembic with the first database schema so later updates preserve user data.
Use portable types and queries. PostgreSQL remains a possible future migration,
not a current dependency or a guaranteed drop-in replacement.

The initial entities are `Category`, `Source`, `Article`, and `CollectionRun`.
Each source has one category. Articles inherit that category. Preserve the
original URL and publication date separately from acquisition time and deduplication keys.

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

Only phase 1 belongs to the initial scaffold. Add libraries and directories when
their phase needs them. shadcn/ui, routing, and server-state utilities can enter
with the interactive frontend. No paid API, LLM, Docker, distributed queue, or
external database service is required for the planned MVP.

Before server deployment, design authentication, HTTPS, backups, and process
management in a separate task. Loopback defaults alone are not a public deployment design.
