# Multiuser model and permissions

The catalog is shared among authorized application users. Sources, categories, articles, and collection history have no individual owner.
Each source still has at most one shared category. Only administrators can change the catalog.
Subscriptions and article read states belong to individual users. Administrator status does not grant access to another user's personal data through the API.

## Roles and access

| Operation | Active reader | Active administrator |
| --- | --- | --- |
| Browse sources, categories, and shared articles | Yes | Yes |
| Follow or unfollow a source | Own subscriptions only | Own subscriptions only |
| Set an article's read status | Own state only | Own state only |
| Create, change, disable, or delete sources | No | Yes |
| Create, change, assign, or delete categories | No | Yes |
| Refresh a source | Followed and globally enabled sources | Any globally enabled source |
| View shared collection history | Yes | Yes |
| Change application accounts or roles through HTTP | No endpoint | No endpoint |

Unknown and inactive users cannot access data endpoints. New application records default to `reader` and inactive.
Activation must be explicit. No first-registration administrator rule exists.
The backend loads role and active status from the application database on every request.
It does not accept these values from client JSON, query parameters, headers, or Supabase user metadata.

The automatic collector remains shared and processes enabled sources even when nobody follows them.
Manual refreshes share the existing cooldown and collection lock across users.
The authorization lookup releases its transaction before a download starts. Use one backend process and one worker per database.

## Personal behavior

`GET /api/articles` defaults to followed sources. `subscribed_only=false` includes the full shared archive.
A subscription is a personal feed choice, not an access grant to an otherwise private article.
Existing category, source, search, read-state, ordering, and pagination filters still combine.
Every response and read-state filter uses the current user's state, including full-archive requests.

An `article_read_states` row means read. A missing row means unread.
Marking an article unread deletes only the current user's state row.
Unfollowing a source leaves article read states intact. Following it again restores the same personal reading history.
New readers receive no subscriptions or copied read states. Their source selection belongs to the later onboarding step.
Creating or importing a catalog source does not subscribe other users or the administrator automatically.

Disabling a source stops collection globally but preserves existing articles, subscriptions, and read states.
Deleting a category leaves its sources uncategorized. Deleting a source removes its articles, history, subscriptions, and associated read states.
Deleting an application user removes only that user's subscriptions and read states. It does not delete shared content.
Prefer source deactivation when permanent deletion is unnecessary.

## Schema and migration

The shared models work on SQLite and PostgreSQL:

- `app_users`: UUID identity, display name, `admin`/`reader` role, active status, and creation timestamp.
- `subscriptions`: composite primary key `(user_id, source_id)` and creation timestamp.
- `article_read_states`: composite primary key `(user_id, article_id)` and read timestamp.

Foreign keys cascade personal data cleanup. Indexes on `source_id` and `article_id` support reverse lookups and deletion.
The application uses conflict-safe inserts for repeated subscription and read requests.
Preliminary reads finish before personal writes, so concurrent SQLite requests do not attempt competing read-to-write lock upgrades.

Revision `0003` leaves shared catalog IDs, article data, category edits, and collection history intact.
It explicitly creates the reserved local owner `00000000-0000-0000-0000-000000000001` as an active administrator.
It follows all existing sources for that owner, including disabled sources, and copies only existing true read flags to personal rows.
The migration then removes `articles.is_read`. It does not copy those flags to future readers.
Timestamps on migrated subscriptions and read states record the migration time, not the original unknown action time.
Repeated upgrades do not restore subscriptions the owner subsequently removed.

The reserved owner has no Google account or Supabase identity attached yet.
The authentication step must explicitly link the owner's verified identity to this profile and preserve its data.
Do not assign this profile to the first person who signs in.

SQLite requires version 3.35 or later for native `DROP COLUMN`.
This avoids a table rebuild that could cascade deletion of related data.
The new PostgreSQL tables remain in `tnr`. The migration revokes their privileges from `PUBLIC` and existing Data API roles.
No Supabase project or personal database is changed merely by installing the code.

Apply migrations explicitly with the [development commands](development.md#initialize-the-database).
Back up the local database before upgrading existing data. Do not apply migrations while the backend is running.
Downgrading to `0002` is destructive: it discards profiles and subscriptions, and restores only the reserved owner's flags to articles.
Use downgrade tests only on disposable databases.

## Local testing before authentication

The backend denies data requests by default. Health and optional API documentation remain available.
For local development, set this value in the private root `.env` after migration:

```dotenv
TNR_LOCAL_USER_ID=00000000-0000-0000-0000-000000000001
```

Restart the backend on `127.0.0.1`. All local requests then use this one application profile.
This setting is a development identity adapter, not a password or login mechanism.
It rejects non-loopback clients and bearer tokens. It never reads user-selection headers or query parameters.
A public proxy can make remote requests appear local, so never enable this adapter on Render or behind a public proxy.
Do not run multiple backend instances to simulate different users against the same database.

The frontend is unchanged in this step. Login, account switching, role-aware controls, and source-selection onboarding are not available yet.
For subscription tests, use the local `/docs` interface:

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

## Verification and next boundary

Backend tests create real Alembic schemas on temporary SQLite files or isolated PostgreSQL databases.
They use one app with an administrator and two reader profiles. Only the tests override the identity adapter to select clients.
No test impersonation header or endpoint exists in the application.
Checks cover personal isolation, administrative denials, inactive users, shared cooldowns, concurrent idempotence, and migration preservation.
Existing downloader, collector, scheduler, search, and pagination tests remain part of the suite.

Validation on 2026-11-06:

- SQLite 3.53.4: 242 tests passed; two PostgreSQL-only tests skipped.
- PostgreSQL 17.11 in an isolated local container: all 244 tests passed.
- Ruff lint and format checks passed. Dependency checks found no broken requirements.
- Migration tests verified data preservation and removal of inherited Data API table grants.
- No frontend files changed, so frontend checks were not run. No personal or hosted database was migrated.

Supabase JWT verification, Google login, invitation provisioning, and browser sessions remain outside this step.
Replace the local adapter with a verified identity provider before enabling external access.
Authorization must continue to use the application's role and active status, not user-editable metadata.
See [Supabase user metadata guidance](https://supabase.com/docs/guides/database/postgres/row-level-security).
Direct PostgreSQL connections do not automatically apply end-user RLS identity. The current boundary is the backend plus the private schema and database grants.
