# PostgreSQL support

SQLite remains the default database. PostgreSQL uses the same SQLAlchemy models, services, API routes, collector, and scheduler.
No cloud account or Docker installation is necessary for SQLite development.
Changing the database URL does not transfer existing data. Keep the local SQLite database intact.

Database support includes the [multiuser data model and backend permissions](multiuser.md).
Authentication, deployment, and data transfer require separate work.
Keep the backend on loopback with one process and one worker. The collector lock is process-local on both databases.

## Connection configuration

The backend uses synchronous Psycopg 3 through SQLAlchemy.
Install the generated backend dependency lock as described in the [development guide](development.md#setup).
The binary driver includes libpq, so a PostgreSQL compiler or system client is not required.

Set `TNR_DATABASE_URL` in private `.env` configuration or backend environment variables.
URLs starting with `postgres://`, `postgresql://`, or `postgresql+psycopg://` select Psycopg 3.
Use generic examples from `.env.example`. Never put a database password in Git or a `VITE_*` variable.
Percent-encode reserved characters in the password and certificate path. Do not log the complete URL.

For Supabase, copy the **Session pooler** endpoint from the project's Connect panel.
Use port `5432`. The shared pooler supports IPv4 and session state.
This application rejects port `6543`, because transaction pooling cannot preserve its session configuration.
The driver keeps prepared statements enabled for direct connections and session pooling.

Remote connections require `sslmode=verify-full`, which is also the default.
Download the project's CA certificate through the Supabase dashboard and set `sslrootcert` to its absolute local path.
The certificate must exist in the backend environment. Keep it outside tracked project files.
The driver verifies the certificate chain and the endpoint hostname. Do not replace verification with `require` or `disable` after a certificate error.
Local test connections can explicitly use `sslmode=disable` with a loopback hostname or address.

Each application engine permits three connections with no overflow, a ten-second pool wait, and a default ten-second connection timeout.
SQLAlchemy checks connections before reuse and recycles them after five minutes.
The pool opens connections only when needed. Migration commands use a separate, short-lived engine.
Review the project's actual Supabase connection quota before deployment. These settings do not represent a hosted-plan guarantee.

Official references, checked on 2026-11-06:

- [Supabase connection methods, session pooling, and TLS](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement)
- [SQLAlchemy Psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#psycopg)

## Migrations and the private schema

PostgreSQL application tables and `alembic_version` live in the fixed `tnr` schema.
Connections set `search_path` to `tnr` and the session timezone to UTC.
They do not fall back to `public` for application tables.
Alembic creates the namespace in the migration transaction before it runs the unchanged revision `0001`.
Revision `0002` adapts PostgreSQL types and constraints. It performs no SQLite table changes.
Revision `0003` adds application users and personal data on both databases. It preserves the reserved local owner's existing read flags.

Set `TNR_MIGRATION_DATABASE_URL` to an owner connection when the application uses a restricted database role.
Alembic uses this URL only for explicit migration commands. If unset, it uses `TNR_DATABASE_URL`.
Use a direct connection for migrations where reachable. Session pooling is the IPv4 alternative.
Both connections must target the same database. The API never reads the migration URL to connect, creates tables, or applies migrations.

For an authorized target, run these commands from `backend/`:

```sh
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic check
```

The expected revision is `0003 (head)`. Applying these commands to Supabase requires separate owner authorization.
This implementation does not move application tables from an existing PostgreSQL `public` schema.
Do not use it to stamp or adopt an unrelated database. Review that case separately.

Downgrades are for disposable databases. A downgrade to `0001` can reject long Unicode keys that do not fit a B-tree.
Downgrading `0003` discards user accounts and subscriptions, and retains only the reserved owner's read flags in the single-user schema.
PostgreSQL rolls back that migration transaction. A downgrade to `base` removes application data but retains the private namespace.

## Data API and database privileges

Keep `tnr` out of the Supabase Data API's exposed schemas. If no feature needs the Data API, disable it during an authorized setup.
Supabase Auth does not require exposing these application tables.
Revision `0002` revokes schema, table, and sequence privileges from `PUBLIC` and existing `anon`, `authenticated`, and `service_role` roles.
Revision `0003` also revokes table privileges on the new personal tables, including inherited default grants to these API roles.
It does not change the `public`, `auth`, or `storage` schemas or create cloud roles.
The schema boundary remains necessary for future tables, including tables that inherit broad project default grants.

Use a separate login role for the backend before deployment. It needs `USAGE` on `tnr` and `SELECT` on `app_users`.
It needs CRUD on catalog, collection, subscription, and read-state tables, plus `USAGE` on their sequences.
Account and role administration is a separate privileged operation, not a public API in this step.
It must not own the schema or tables, inherit privileged roles, or have `SUPERUSER`, `BYPASSRLS`, `CREATEROLE`, or `CREATEDB` privileges.
Keep schema ownership and DDL permissions on the migration connection.
Provisioning roles, passwords, grants, and Data API settings remains an explicit cloud-setup task.
Do not run the application as the supplied Supabase `postgres` owner in a public deployment.

RLS is not the access boundary in this step. No per-user policies exist yet.
Owners and roles with `BYPASSRLS` can bypass RLS. SQL connections do not acquire end-user authorization from Supabase Auth automatically.
FastAPI checks active users and roles, but its temporary local identity adapter is not authentication.
Verified Supabase identities and invitation management remain necessary before public deployment.

See [Supabase Data API security](https://supabase.com/docs/guides/api/securing-your-api) and
[PostgreSQL row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

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

## Isolated PostgreSQL tests

The default test command still uses temporary SQLite files initialized through real Alembic migrations.
Add `--postgres` to run the same suite against a disposable local PostgreSQL server.
The fixture requires a literal loopback address and refuses remote hosts, including Supabase hosts.
It creates a unique `tnr_test_*` database for each database test and drops only that generated database afterward.
The supplied database is used only to create and drop test databases. Use a local test role with `CREATEDB`.
Never forward the test port to a personal or remote database.

With an existing disposable PostgreSQL server, set `TNR_TEST_POSTGRES_URL` to its administrative connection URL.
This variable is not read from `.env` and has no application effect.
Run from the repository root:

```sh
TNR_TEST_POSTGRES_URL='postgresql+psycopg://postgres:tnr-local-test-only@127.0.0.1:55439/postgres?sslmode=disable' \
  backend/.venv/bin/pytest backend/tests --postgres
```

Docker is an optional way to supply that server. These commands use a disposable container without a persistent volume:

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

The PostgreSQL-support step validation on 2026-11-06 used Python 3.13.3, Psycopg 3.3.8, and PostgreSQL 17.11 in the optional container:

- SQLite: 222 tests passed. Two PostgreSQL-only checks were skipped.
- PostgreSQL: all 224 tests passed, including execution of the exported Alembic SQL.
- Ruff lint and format checks passed. `pip check` found no broken requirements.
- No generated test databases remained. The disposable container was removed after validation.

No personal SQLite database or Supabase project was migrated during these checks.
