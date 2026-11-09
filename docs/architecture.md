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
See [PostgreSQL configuration and tests](deployment.md#postgresql-configuration) for privilege boundaries and isolated validation.
No existing data is transferred, and no Supabase configuration is applied automatically.

Revision `0004` adds a unique Supabase identity link. Operator commands approve readers or link the reserved owner.
Revision `0005` adds administrator email invitations and transactional reader creation after verified Google identity checks.
Existing profiles and revoked status take precedence. No HTTP route changes roles or assigns the owner.
See [authentication and access approval](authentication.md).

Revision `0003` adds `AppUser`, `Subscription`, and `ArticleReadState`.
It moves existing read flags to the reserved local owner and removes the global article flag.
Sources and categories belong to the catalog. Only administrators can change them.
Subscriptions and read states belong to individual users, including administrators.
See [multiuser ownership and permissions](authentication.md#user-roles-and-personal-data) for the complete contract and migration behavior.

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
destination addresses. Only collection paths use the guarded downloader for outbound feed requests.

Changing a feed URL clears its cache validators and current diagnostics. Existing
articles and collection history remain attached to the source. Disabling a source
preserves its articles. No collection runs are created by these API operations.

## Manual collection

`POST /api/sources/{id}/refresh` waits for the collection result. It writes a
`running` record, closes the transaction, downloads and parses the feed, then commits
new articles and the final outcome together. A failure rolls back article inserts
and records an error in a separate transaction. Storage outages can prevent that
last write. Interrupted runs are closed on the next refresh of the same source.

An application gate rejects concurrent collections and source PATCH/DELETE requests.
A PostgreSQL session advisory lock or SQLite OS file lock also coordinates separate collector instances.
Network access holds no database transaction. PostgreSQL reserves one pool connection for the session lock.
Locks release on process/connection closure and remain held during suspension, without expiring lease overlap.
Keep one backend process/worker. External SQL edits do not participate in this gate.

Revision `0010` adds `sources.last_attempt_at` and backfills it from collection history.
The collector commits that timestamp and increments the failure counter before HTTP. Success resets the counter.
The shared minimum is 900 seconds after the later of the latest attempt and completed check.
Error backoff is `max(900, min(3600, 30 × 2^min(failures, 7)))` seconds, including interrupted attempts.
Source URL changes preserve these limits. Rejected requests create no collection runs.
Automatic collection also respects each source's configured interval.

`POST /api/sources/refresh` selects authorized sources on the backend and returns aggregate counts.
Administrators can refresh the enabled catalog. Readers can refresh only followed sources.
Active access and subscription checks repeat before each download. Never-attempted and oldest sources have priority.
The request holds the shared gate for up to 10 sequential attempts with a 45-second collection budget.
Remaining time bounds each download. Parsing and database work can extend response time.
The frontend reloads its current article query even when no source is eligible or the request fails.
There is no queue, automatic frontend retry, AI dispatch, or retention change.
See [exact rules and UI behavior](development.md#refresh-from-news).

The downloader uses HTTPX, public IP checks, and at most three redirects. Each hop
connects to an already validated IP, with the original Host header and TLS hostname.
This uses HTTPX's documented [SNI extension](https://www.python-httpx.org/advanced/extensions/#sni_hostname).
Mixed public/private DNS answers, special IP ranges, nonstandard ports, and HTTPS
downgrades are rejected. Environment proxies and credentials are not used.
Only the first validated DNS address is attempted. DNS runs in a bounded child process with no inherited environment. Timeout terminates and reaps it before the next feed.

HTTP operations and DNS waits have a maximum timeout of 10 seconds.
An absolute HTTP deadline of at most 30 seconds cancels slow headers and bodies.
A manual batch supplies its remaining budget when that is shorter.
The DNS child cannot start HTTP. Timed-out DNS work is terminated, and HTTP work is cancelled before the collector advances.
Downloads are streamed and limited to 2 MB by default.
The client requests uncompressed content but also accepts gzip with bounded decompression.
The same size limit applies separately to transferred and decoded bytes. Invalid,
truncated, trailing, or concatenated gzip streams are rejected. Other encodings,
authentication, private networks, and nonstandard ports
are not supported in this version.

ETag and Last-Modified support conditional requests. A `304` preserves articles and
records `not_modified`. Without conditional support, the server can send the full feed for local deduplication. Cache headers change only after successful collection.
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

After each poll delay, the worker reads enabled source IDs, ordered by never-attempted and oldest attempt time.
It closes that session before collection. `Collector.refresh_if_due` acquires the shared
lock and rereads source settings before it calls the existing collection path.
A source is due after the later of its latest attempt and completed check, plus the greater of its interval and cooldown.
Never-checked sources are due immediately. Missing, disabled, and unexpired sources are skipped.
The source interval defaults to 60 minutes. The poll delay defaults to 30 seconds.

Each pass is sequential. A busy collector defers the remaining pass. Source failures
leave other sources available, and scan failures are logged without stopping the worker.
The next pass starts after the current pass and poll delay. Missed intervals do not create jobs.
Stored check and attempt times preserve the schedule across restarts.
Normal shutdown signals the worker, waits for its active feed, then disposes the engine.
The lifespan waits for that join outside the event loop. DNS waiting and HTTP work have separate bounds.

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

### Reader workflow

Open **Le mie fonti → Proponi una fonte**, or use the navigation entry.
Enter a name. The website/feed URL, note, and suggested category are optional.
Select **Segui questa fonte se approvata** only if you want that personal subscription.
The checkbox is initially clear. Submission does not create a source or start collection.
The list shows only your proposals, including decisions and rejection reasons.
Cancel a pending proposal with **Annulla proposta**. Cancellation preserves its record.
Italian and English are available through the existing account menu.

Limits are 200 characters for names, 2,048 for URLs, and 500 for notes and rejection reasons.
Each user can have at most five pending proposals. Completed proposals do not count toward this limit.
A normalized, case-insensitive name cannot appear twice among the same user's pending proposals.
The database enforces this duplicate rule. The transaction gate enforces the pending limit during concurrent requests.
The API applies these limits to administrators who submit proposals directly, too.

### Administrator workflow

Open **Proposte**. Its counter comes from the database, rather than browser storage.
The counter loads at sign-in and refreshes after operations and on focus, visibility return, or page restoration.
Return events have a 30-second debounce. There is no interval polling or realtime service.
A failed counter request displays `?`; it does not assert that no proposals exist.
Use **Aggiorna elenco** to refresh the list and counter explicitly.

The initial filter shows pending proposals. Select another status to inspect previous decisions.
Each entry includes the proposer, original name, optional URL and note, suggested category, date, and status.
Select **Valuta proposta**, then choose one of these actions:

- Correct the name, supply an RSS/Atom feed, choose the category, and explicitly approve.
- Link an existing catalog source. Its settings, including disabled collection, remain unchanged.
- Reject with a required reason, visible to the proposer.

New-source approval validates downloaded bytes with the existing protected downloader and RSS/Atom parser.
It uses the existing redirect, address, TLS, timeout, size, XML, and entry limits.
Submission performs URL syntax checks only. It does not resolve DNS, fetch a website, or discover feeds.
As with collection, the operating system's DNS resolution has no hard application deadline.
No articles are imported during approval. A new enabled source becomes eligible for normal collection.
An exact existing feed URL links its source without another download or configuration change.

### State, ownership, and transactions

`pending` can become `approved`, `rejected`, or `cancelled`. Terminal states cannot change.
Repeating an approval returns the original approved result, even if the repeated payload names another target.
Repeating cancellation or the same rejection is also harmless. Conflicting terminal operations return `409`.
The decision records its time and actor. Approval retains the approved name and feed URL as a historical snapshot.
Source deletion clears the live reference but preserves that snapshot and the decision.
Category deletion clears the suggestion. An explicitly selected category that disappeared causes `404` without partial approval.
A revoked proposer cannot be approved. The administrator can reject the proposal instead.
The backend rechecks proposer access after validation, before committing approval.

PostgreSQL uses one transaction-scoped advisory lock for proposal writes and operator
revocation, activation, and profile deletion. The lock is held through commit or rollback.
If approval acquires it first, approval finishes before revocation can commit.
If revocation acquires it first, approval waits, reads the revoked state, and returns `409`
without creating a source, decision, or subscription. Network validation holds no such lock.
SQLite first executes an empty UPDATE to acquire a write reservation before reads in its PEP 249 transaction.
These gates serialize pending counts and decisions. Constraints independently prevent duplicate feeds and subscriptions.
Approval stores the source, decision, and optional personal subscription in one transaction.
HTTP validation runs outside that transaction. Approval also uses the collector's existing source-operation gate.
Concurrent HTTP approvals can receive `409` while that gate is occupied; a later retry returns the saved result.
Use one backend worker and instance, as required by the collector.
Run access commands from this release too: an older operator checkout or a direct SQL
UPDATE does not participate in the shared advisory lock. No runtime role privileges are added.

Authorization uses the existing Google/Supabase identity and active application profile.
Readers cannot approve, reject, inspect another reader's proposals, or modify another person's subscriptions.
The optional subscription belongs only to the proposer and never changes other users' choices.
No endpoint grants a role or changes identity links, invitations, or read states.
Private SQL connections do not carry an end-user identity: ownership checks remain in FastAPI.
The new table is not exposed through Supabase's Data API.

### Proposal API

| Method | Path | Access |
| --- | --- | --- |
| GET | `/api/proposals?status=pending&limit=20&offset=0` | Own records for readers, all records for administrators |
| POST | `/api/proposals` | Active users; name required |
| POST | `/api/proposals/{id}/cancel` | Proposer only, pending state |
| POST | `/api/proposals/{id}/approve` | Administrator; existing `source_id`, or `name`, `feed_url`, optional `category_id` |
| POST | `/api/proposals/{id}/reject` | Administrator; required `reason` |

Lists use existing pagination, with a maximum page size of 100.
Unknown fields are rejected. Client-supplied user IDs, statuses, or decision timestamps cannot set ownership or decisions.
Notifications consist of in-app feedback and the persistent result list. No email, push, or external messaging is used.
Proposal records have no automatic expiry in this release. Deleting a reader cascades deletion of their proposals.
The public privacy pages describe these fields, access, cancellation, and retention in both languages.

Publication and grants are covered in [deployment](deployment.md#source-proposal-rollout).

## Shared hourly AI digest — local implementation

The optional [hourly digest](ai-briefs.md) shares saved public RSS summaries across the catalog.
The fixed model is paid Gemini 3.1 Flash-Lite through the direct Google Developer API.
Generation and explicit budget-risk acceptance default to disabled. No alternative provider or automatic fallback exists.
Revision `0007` adds jobs and control, `0008` adds unique hourly editions, and `0009` adds the exact monthly monetary ledger.
Admission, quota, money, and dispatch ownership use persistent database transactions.
The reservation budget is USD 2.00 per calendar month UTC, distinct from the Google EUR cap.
It is a prudential consumption control, not a guaranteed maximum Google invoice.
Reads never call a provider. Personal subscriptions, identities, and reading states never enter prompts.
The inactive workflow uses an operator credential. No new queue infrastructure or local LLM is added.

## Starter sources

Verification date: **2026-11-05**. Each included URL returned RSS/Atom with usable
articles through the application's guarded downloader and parser. Availability can change.
This catalog stores source metadata only. Article content retains the publisher's rights.

| Source | Verified feed | Initial category |
| --- | --- | --- |
| OpenAI | <https://openai.com/news/rss.xml> | Artificial intelligence |
| Google DeepMind | <https://deepmind.google/blog/rss.xml> | Artificial intelligence |
| Hugging Face | <https://huggingface.co/blog/feed.xml> | Open models |
| Mistral AI | <https://mistral.ai/news/rss> | Open models |
| Salvatore Sanfilippo (antirez) | <https://antirez.com/rss> | Software engineering |
| Simon Willison | <https://simonwillison.net/atom/everything/> | AI agents |
| Hacker News | <https://news.ycombinator.com/rss> | Software engineering |
| arXiv — Artificial Intelligence | <https://rss.arxiv.org/rss/cs.AI> | Research |
| MacRumors | <https://feeds.macrumors.com/MacRumors-All> | Technology companies |
| TechCrunch | <https://techcrunch.com/feed/> | Technology companies |
| Wired Italia | <https://www.wired.it/feed/rss> | International technology |

The arXiv feed covers `cs.AI`, not all arXiv subjects. Hacker News links to submitted
articles, which can come from other publishers. Category assignments are editable suggestions.
The antirez source covers his blog. GitHub and YouTube integrations remain future work.

### Sources not imported

- **Anthropic:** [News](https://www.anthropic.com/news) is accessible, but no working official RSS/Atom feed was verified.
  The checked `/news/rss.xml` and `/rss.xml` endpoints returned HTTP 404.
- **Reuters Technology:** [Technology](https://www.reuters.com/technology/) remains a requested source.
  The legacy `https://feeds.reuters.com/reuters/technologyNews` hostname did not resolve during the check.
  No working public replacement was verified. Thomson Reuters investor feeds cover a different subject.

These observations do not prove that no feed exists. A Feedly subscription can use a
different integration. An exported Feedly OPML file or exact feed URL can support a later check.
No third-party scraper, paid feed service, or unofficial replacement is included.

### Import and edit

Follow the [local setup instructions](development.md#use-the-interface).
The catalog is in [source_catalog.json](../backend/app/source_catalog.json).
Import is explicit and matches feed URLs. Existing settings remain unchanged.
Use **Fonti** to edit, disable, delete, or refresh imported sources.

To propose another default, verify its URL through the collector first.
Record the verification date and category, then update the catalog and this table.
Automated tests use local fixtures and mocked HTTP. They do not require these sites.

## Database behavior

- Dates use PostgreSQL `timestamptz` or SQLite naive UTC storage. Python and API responses use aware UTC on both databases.
- Migration `0002` interprets earlier PostgreSQL timestamps as UTC explicitly. Naive Python datetime input remains invalid.
- Booleans, foreign keys, check constraints, null GUIDs, and cascade behavior retain the existing contract.
- PostgreSQL `C` collations preserve SQLite's byte ordering and ASCII case behavior for searchable and ordered text.
- Search remains a literal substring search. Wildcards are escaped. Non-ASCII case variants remain distinct.
- Article order still uses publication time, then acquisition time when absent, with descending IDs for ties.
- Existing foreign-key and date indexes remain. Leading-wildcard text search does not gain an index in this step.
- PostgreSQL uses exact hash exclusion constraints for feed URLs and source-scoped article GUIDs and URLs.
  These constraints recheck original values, including hash collisions. They permit long UTF-8 values without B-tree size failures.
  SQLite keeps its existing unique constraints. No hash extension or alternate collector implementation is required.
- Alembic does not automatically compare exclusion constraints. Dedicated tests check their presence and duplicate rejection.
  Review changes to these three constraints manually in future migrations.

See [PostgreSQL B-tree limits](https://www.postgresql.org/docs/17/btree.html) and
[exclusion constraints](https://www.postgresql.org/docs/17/sql-createtable.html#SQL-CREATETABLE-EXCLUDE).
