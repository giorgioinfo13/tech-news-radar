# Publication preparation

This is a preparation guide, not a record of a deployment. No cloud database,
role, service, domain, or account setting is assumed to exist. Use the existing
Supabase Auth project to retain user UUIDs. Keep the current SQLite database and
private local `.env` unchanged until the separate data-transfer phase is approved.

## Architecture and boundaries

The browser loads the Vite build from Vercel. Requests to `/api/*` go through a
Vercel external rewrite to the same path on Render. The frontend never receives
a database password or collection secret. Render connects to Supabase PostgreSQL
through the **session pooler on port 5432**, with a verified CA and a dedicated
`tnr_app` login. The private application schema is `tnr`.

The browser sees one API origin. Do not add wildcard CORS or a production
`VITE_API_URL`. `TNR_API_TARGET` is only a Vite development setting. The Render
URL remains public: all data routes still require JWT verification and an active
application profile. CORS is not access control. The collection route has its
own secret; the GitHub workflow calls Render directly, avoiding Vercel's proxy
request limit. Keep **one worker and one service instance**.

The frontend waits up to 90 seconds for API requests. A sleeping Render Free
instance can take about a minute to wake; Vercel's external proxy limit is 120
seconds. There is no automatic replay of writes. After an uncertain write,
refresh the state before trying it again. API responses forbid browser and CDN
caching; the Vercel template also disables external-rewrite caching. No service
worker caches API responses or tokens.

## Files prepared for review

| File | Purpose |
| --- | --- |
| `deploy/render.yaml.example` | Python service settings; importing a Blueprint is a deploy operation |
| `deploy/vercel.json.example` | API proxy, cache policy and response headers; replace the backend hostname first |
| `frontend/vercel.json` | Prepared Vercel configuration for the verified Render hostname; automatic Git deployments disabled |
| `backend/sql/create_app_role.sql` | One-time, separately authorized database-role setup after migrations |
| `backend/sql/check_app_role.sql` | Read-only inspection of role and schema access |
| `scripts/backup_sqlite.py` | Private, consistent SQLite backup with integrity checks; refuses overwrites |
| `backend/app/transfer.py` | Local-only SQLite-to-PostgreSQL rehearsal with row verification and transactional rollback |
| `backend/app/transfer_supabase.py` | Offline transfer plan, read-only remote checks, and explicit execution against a pinned Supabase target |
| `frontend/public/privacy.html` | Public explanation of authentication, personal data and deletion requests |

The `.example` templates are not active hosting configuration files.
`frontend/vercel.json` will apply when Vercel builds this frontend. Its presence
does not mean that a frontend deployment exists. Do not deploy without separate
approval. The current head is `0005`.
For an existing `0004` deployment, follow the [invitation rollout](authentication.md#invite-friends-by-email) before deploying this version.

## Environment map

Set values in each provider's private configuration, never by uploading the
local `.env`. Vite variables are embedded in the public build. Changing them
requires rebuilding the frontend. Leave them unset for unapproved preview
builds; do not allow wildcard OAuth redirect URLs.

| Variable / file | Destination | Value and purpose | Sensitivity |
| --- | --- | --- | --- |
| `TNR_ENVIRONMENT` | Render | `production`, enables startup configuration guards | Public |
| `TNR_DOCS_ENABLED` | Render | `false` | Public |
| `TNR_SCHEDULER_ENABLED` | Render | `false`, external collection for sleeping instances | Public |
| `TNR_SUPABASE_URL` | Render | `https://PROJECT_REF.supabase.co`, JWT issuer/JWKS | Public |
| `TNR_SUPABASE_PUBLISHABLE_KEY` | Render | Same public project key as the frontend, for Google invitation verification | Public |
| `TNR_DATABASE_URL` | Render | SQLAlchemy URL for `tnr_app.PROJECT_REF` through the session pooler | **Secret**, includes password |
| `supabase-ca.crt` | Render secret file | CA from the project, available as `/etc/secrets/supabase-ca.crt` | Public certificate; private configuration file |
| `TNR_COLLECTION_TRIGGER_SECRET` | Render and GitHub Actions secret | Same random URL-safe value, 32–128 characters; activate only after hosting checks | **Secret** |
| `TNR_BACKEND_URL` | GitHub Actions variable | Stable `https://SERVICE.onrender.com`, no `/api` suffix | Public |
| `TNR_COLLECTION_ENABLED` | GitHub Actions variable | Absent/false until activation is approved, then `true` | Public |
| `VITE_SUPABASE_URL` | Vercel Production | Same Supabase origin as the backend | Public |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Vercel Production | Corresponding `sb_publishable_…` key | Public; never a secret/service-role key |
| `TNR_MIGRATION_DATABASE_URL` | Operator environment only | Privileged connection for Alembic and account provisioning | **Secret**; forbidden in the production web service |

Omit `TNR_LOCAL_USER_ID`, `VITE_LOCAL_MODE`, and operator credentials from hosting.
Keep feed limits at their existing defaults unless measured results require a
change. Use a separate operator shell/environment for migrations and access
commands; do not point the running local app at the remote database.

Example application connection, with placeholders only:

```text
postgresql+psycopg://tnr_app.PROJECT_REF:ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=verify-full&sslrootcert=/etc/secrets/supabase-ca.crt
```

Percent-encode the password. Obtain the exact pooler hostname and region from
Supabase's Connect panel. Do not use transaction pooling on port 6543, a database
owner, or `sslmode=require`. The production guard checks the URL, not the actual
role grants or the certificate's validity; those need the checks below.

## Separate approval gates

### 1. Database configuration and schema

Read [PostgreSQL](postgresql.md). Record the project, server version, region,
current migration state and backup destination privately. Verify that Auth uses
ES256/RS256. Do not create another project merely to deploy the app.

Before any remote writes, review and approve the specific target and operations:
Alembic schema migration, application-role creation, password setup, and Data API
configuration. These are distinct from copying local data. The remote migration
command, from `backend/` in the dedicated operator environment, is:

```bash
.venv/bin/alembic current
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Review offline SQL first if required (`alembic upgrade head --sql` with the
operator URL configured). Do not run migrations in a build, startup command or
Render health check. Alembic seeds the reserved owner; it does not link an Auth
identity or transfer the owner's existing data.

After migration, use `psql -X -v ON_ERROR_STOP=1` with a private connection service
to apply `backend/sql/create_app_role.sql`. This one-time script refuses an
existing `tnr_app` role. Set its password separately with `\password tnr_app` in
psql so it is not in a SQL file or shell history. Inspect an existing role instead
of dropping/recreating it. Run `backend/sql/check_app_role.sql` and verify:

- Login is true; superuser, database/role creation, replication, bypass-RLS and
  inheritance flags are false. There are no memberships permitting `SET ROLE`.
- Schema USAGE is true, CREATE is false; the role owns no `tnr` objects.
- `app_users` permits SELECT and reader-only INSERT, constrained by the migration `0005` RLS policies.
  Seven data tables permit SELECT/INSERT/UPDATE/DELETE. `alembic_version` has no runtime access. Sequences permit USAGE only.
- `anon`, `authenticated` and `service_role` have no `tnr` schema/table access.
- `tnr` is not in Data API exposed schemas. Disable the Data API if unused by
  other project applications; this app uses direct SQL and Supabase Auth.

Check the grants again after each migration. There are no default grants to new
tables. RLS does not protect a privileged SQL connection. The backend enforces
per-user access; `tnr_app` is not a per-user database identity.

### 2. Existing-data transfer, separately authorized

Do not start with an empty online account and discard the local owner's data.
Prepare a transfer against a **copy** first. Approval must name the source
snapshot, exact target, expected counts, and rollback plan. The importer itself
must be reviewed and tested in that phase; this guide does not authorize a copy.
The rehearsal command still refuses remote targets. The separate Supabase
command below prepares a plan offline. Its remote operations require explicit
authorization. Preparing a plan does not connect to Supabase or authorize a copy.

1. Stop local writes and the collector during the final snapshot/cutover. Make
   the SQLite backup below and record its SHA-256, Alembic head, and counts for
   all seven application tables. Verify no collection is still `running`.
2. Apply the real migrations to an isolated temporary PostgreSQL database. It
   must contain only the reserved owner and the eight default categories created
   by the migrations. All other application tables must be empty.
3. Transfer with typed SQLAlchemy values in one transaction: `app_users`,
   `categories`, `sources`, `articles`, `collection_runs`, `subscriptions`, then
   `article_read_states`, then `reader_invitations`. Keep UUIDs, Supabase subjects, primary keys, UTC times,
   active/role flags, source state and personal rows. Update the **same reserved
   owner row** from the snapshot, rather than creating another administrator.
   Reconcile the default categories with the snapshot before inserting sources;
   preserve the snapshot's category IDs and values.
4. Reject target data other than the unchanged migration seeds. Reset the four
   integer sequences to their imported maxima (or initial value for empty tables). Do not copy
   SQLite DDL, internal sequences, or run a `.dump` directly on PostgreSQL.
5. Compare every normalized row, table count, relationship and identity mapping,
   including revoked users, subscriptions and read states. Counts alone are not
   sufficient. Test the next insert, two accounts, permissions and revocation.
6. Repeat the reviewed operation on the approved remote target, then configure
   hosting only after verification. Retain the original SQLite and its backup.
   Prevent simultaneous writes to old and new databases during cutover.

Rollback before online writes can return to the unchanged local database. Once
new online writes exist, do not switch back blindly: export/reconcile them first.
Never reset a remote database or overwrite its data as a deployment retry.

#### Local transfer rehearsal

Use an isolated PostgreSQL server on literal `127.0.0.1` or `::1`, with an explicit
port. An existing local installation is sufficient. Docker is optional.
Create a new database from `template0` with a name such as
`tnr_transfer_20261107`. The command also accepts the test suite's `tnr_test_`
names. Both prefixes require 8–32 lowercase letters or digits after the prefix.
Use a local database owner that can run migrations and restart sequences.

Create a SQLite copy with `scripts/backup_sqlite.py` as described below. Record
its SHA-256. Use a closed copy without WAL or journal sidecars. Never supply the
working database as the rehearsal input. Keep the backup and reports private.

In a dedicated local shell, set `TNR_TRANSFER_DATABASE_URL` privately. Do not
put passwords in shell history. Its format is:

```text
postgresql+psycopg://LOCAL_OWNER:ENCODED_LOCAL_PASSWORD@127.0.0.1:LOCAL_PORT/tnr_transfer_20261107?sslmode=disable
```

This variable is only for the local operator command. Do not set it in hosting
or the application's `.env`. The command does not use `TNR_DATABASE_URL` or
`TNR_MIGRATION_DATABASE_URL`. Remove libpq routing/session overrides such as
`PGHOSTADDR`, `PGSERVICE`, `PGSERVICEFILE`, and `PGOPTIONS` from that shell.

From `backend/`, apply the real migrations to this explicit local target:

```bash
.venv/bin/python - <<'PY'
import os
from alembic import command
from alembic.config import Config
from app.transfer import local_target_url

url = local_target_url(os.environ["TNR_TRANSFER_DATABASE_URL"])
config = Config("alembic.ini")
config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%"))
command.upgrade(config, "head")
PY
```

Run the rehearsal with the recorded checksum and a new private report path:

```bash
umask 077
.venv/bin/python -m app.transfer --snapshot /PRIVATE/PATH/snapshot.db --sha256 RECORDED_SHA256 > /PRIVATE/PATH/new-report.json
```

Choose a nonexistent report filename. Shell redirection can overwrite a file.
Exit status zero and a complete JSON report indicate success. The report contains
the snapshot hash, revision, and counts/hashes for all seven tables. It contains
no credentials, account identifiers, or record contents. A failed command can
leave an empty report. Inspect the disposable target before a retry.

The importer reads the source in read-only mode. It requires revision `0005`,
valid SQLite integrity/foreign keys, and no unfinished collection. It checks
the target's unchanged migration seeds under table locks. It copies typed rows
in batches and compares every column before commit. It reads the snapshot into
memory, so this procedure targets a small personal database, not bulk archives.

The owner retains the reserved UUID and all imported identity fields. Only
unused, unchanged category seeds are replaced. Integer sequences restart at
`max(id) + 1`, or `1` for empty tables. The importer uses transactional
[`ALTER SEQUENCE RESTART`](https://www.postgresql.org/docs/17/sql-altersequence.html),
so a failure rolls back both data and sequence changes. A populated target is
refused. Rehearse again in a new disposable database instead of clearing one.

Run `tests/test_transfer.py` with `--postgres` using the isolated test setup in
[PostgreSQL](postgresql.md#isolated-postgresql-tests). Tests cover complete
row preservation, subsequent inserts, rollback, concurrent-write exclusion,
personal reads/subscriptions, reader permissions, revoked users, and unapproved
users. These API tests substitute verified identities. They do not repeat Google
OAuth or establish behavior on hosted services or installed mobile apps.

#### Supabase transfer plan and execution

The operator command has four separate operations:

| Operation | Network and database effects |
| --- | --- |
| `prepare` | Local file reads only, plus a new private plan file |
| `check` | Remote transaction with `REPEATABLE READ READ ONLY`, plus a private preflight report |
| `execute` | One remote transaction that copies the reviewed snapshot and restarts four sequences |
| `verify` | Remote read-only comparison after execution, including sequence values |

All commands use an explicit private JSON configuration file (mode 0600).
Its `TNR_MIGRATION_DATABASE_URL` field contains the operator connection.
The commands do not inherit application or migration URLs from `.env`.
Keep this file outside Git, for example under `backend/data/deployment/`.
Never print it or pass its password through a command-line argument.

The URL must use `postgres.PROJECT_REF`, a Supabase session-pooler hostname,
port `5432`, database `postgres`, `sslmode=verify-full`, and an absolute CA path.
The plan pins the exact project reference, host, username, and CA checksum.
It also pins the snapshot path/checksum, revision `0005`, and every table's
count and normalized-row checksum. It contains no connection password or
Auth subject values. Store it privately because it includes local paths.

From `backend/`, prepare a plan with the chosen snapshot:

```bash
.venv/bin/python -m app.transfer_supabase prepare \
  --operator-config data/deployment/operator.json \
  --snapshot data/backups/SNAPSHOT.db --sha256 SNAPSHOT_SHA256 \
  --project-ref PROJECT_REF --output data/deployment/transfer-plan.json
```

The command prints the plan's SHA-256. Record it with the reviewed plan.
Preparation checks local inputs only. It does not establish current remote
state, TLS connectivity, identity existence, or application grants.

Before the final transfer, stop local API/collector writes and keep hosting
and external collection inactive. Create and rehearse a final snapshot if the
working database changed. Prepare a new plan for that snapshot. A plan does
not detect later writes to the separate working SQLite database.

After authorization for remote inspection, run:

```bash
.venv/bin/python -m app.transfer_supabase check \
  --operator-config data/deployment/operator.json \
  --plan data/deployment/transfer-plan.json --plan-sha256 PLAN_SHA256 \
  --output data/deployment/transfer-preflight.json
```

The check verifies both TLS hops, database/operator identity, the unchanged
migration seeds, and the restricted `tnr_app` permissions. It rejects PUBLIC
or Data API role access to the application schema/tables. It checks that each
active application's Auth subject exists in this project's `auth.users`.
It does not read profile metadata to assign privileges or modify Auth records.
Confirm Data API dashboard settings separately. No migration command runs here.

Review the private report and its printed checksum. Before authorizing execution,
retain a backup of the remote `tnr` schema with the separate backup procedure.
Record its checksum privately. Keep the original SQLite and its final snapshot.
Approval must identify the project, snapshot, plan checksum, counts, and rollback
procedure. The preflight report must be less than 24 hours old.

Only after explicit approval for that exact transfer, run:

```bash
.venv/bin/python -m app.transfer_supabase execute \
  --operator-config data/deployment/operator.json \
  --plan data/deployment/transfer-plan.json --plan-sha256 PLAN_SHA256 \
  --preflight data/deployment/transfer-preflight.json --preflight-sha256 PREFLIGHT_SHA256 \
  --confirm-project-ref PROJECT_REF --output data/deployment/transfer-executed.json
```

Execution rechecks the pinned files, endpoint, Auth identities, grants, and seeds
under application-table locks. It rejects changes since preflight. It uses the
same copy and verification transaction as the local rehearsal. Runtime grants
are checked again before commit. It does not change Auth records, roles,
passwords, hosting, the local `.env`, or the original SQLite database.

Before starting application writes, verify the committed data:

```bash
.venv/bin/python -m app.transfer_supabase verify \
  --operator-config data/deployment/operator.json \
  --plan data/deployment/transfer-plan.json --plan-sha256 PLAN_SHA256 \
  --output data/deployment/transfer-verified.json
```

Every output must be a new filename. Files use mode 0600 and refuse overwrites.
A failure can leave an empty or incomplete output file. A connection failure
during commit can leave the outcome uncertain: do not automatically execute again.
Use `verify` first. If it fails, inspect the target read-only and compare it with
the preflight seeds. Do not infer rollback solely from a missing success report.

Before new online writes, rollback can keep the application on unchanged SQLite.
Leave remote data intact until its state is understood. Restoring a remote backup
or deleting imported rows requires another explicit, reviewed operation.
After online writes begin, reconcile those writes before switching databases.
The command has no destructive reset or automatic rollback-after-commit option.

The local tests use real PostgreSQL migrations and simulate Supabase Auth and
transport metadata. They verify read-only enforcement, target restrictions,
grant/identity failures, stale reports, drift, rollback, and post-transfer checks.
They do not validate a live pooler, the project's CA, or current cloud settings.
References: [Supabase session pooling and TLS](https://supabase.com/docs/guides/database/connecting-to-postgres)
and [PostgreSQL read-only transactions](https://www.postgresql.org/docs/17/sql-set-transaction.html).

### 3. Render and Vercel deployment, separately authorized

First verify Vercel account/project availability. Select stable domains and
nearby supported regions; no hostname in a template is a provisioned service.

#### Configure without deployment

Render's new Web Service form has no separate save-only action. The final
**Deploy web service** button creates the service and starts its first deployment.
Setting **Auto-Deploy** to **Off** does not prevent that first deployment.
Prepare the form, but leave it unsubmitted until deployment is approved.
Keep a private record of its values because an open form is not persistent configuration.
Do not treat the proposed service name as a confirmed hostname.

Vercel's New Project page offers **Create an empty project** below the import options.
This creates a project without a deployment or Git connection.
Rename the project, then save its build settings and Production environment variables.
Keep the Git repository disconnected during this phase.
Set **Ignored Build Step → Behavior** to **Don't build anything** (`exit 0`).
This setting skips Git builds but does not block every manual deployment method.
Do not use Deploy, CLI deployment, or file uploads during configuration.
Verify **No Production Deployment** and **No Preview Deployments** in the project overview.

Before an approved deployment, connect the intended repository and verify the production branch.
Review the ignored-build setting before changing it, including its effect on preview builds.
Keep preview credentials unset and approve the intended deployment method separately.
Record account-specific settings and credential paths outside Git.

The repository configuration also sets `git.deploymentEnabled` to `false`.
This disables automatic Git deployments for all branches, including previews.
Keep this setting until automatic publication is separately approved.
It does not prohibit an explicitly requested manual deployment.

References: [Render service creation](https://render.com/docs/web-services)
and [Vercel project management](https://vercel.com/docs/projects/managing-projects).
See [Vercel Git configuration](https://vercel.com/docs/project-configuration/git-configuration)
for the repository-level deployment switch.

#### Deployment settings and verification

Render: use the repository root, Python 3.13 from `.python-version`, and the
commands in the template. `pip install -r backend/requirements.txt` uses pinned
requirements. The start command binds `$PORT` on `0.0.0.0`, with one Uvicorn
worker and access logs disabled. No disk stores application data. Upload the CA
and set the private environment before deploying. Auto-deploy is off in the
template, but initial Blueprint creation still deploys. Keep it manual.

Vercel: set Root Directory to `frontend`, framework Vite, Node 24.x, install
`npm ci`, build `npm run build`, output `dist`. Enable inclusion of files outside
the Root Directory: the frontend imports branding assets from `docs/assets`.
The prepared `frontend/vercel.json` routes `/api/:path*` to
`https://tech-news-radar-api.onrender.com/api/:path*`.
For another installation, copy `deploy/vercel.json.example` and replace its backend placeholder.
This file contains no secrets and can be committed after review. Static JSON does not interpolate
an environment variable into the rewrite. The app uses hash navigation; OAuth
returns to `/`, so there is no need for a blanket rewrite of missing assets to
HTML. Keep Git deployments/previews disabled until their publication is approved.

Before the first frontend deployment, commit and push the reviewed configuration.
Verify that the selected remote commit contains `frontend/vercel.json`.
Confirm the assigned frontend domain before updating the OAuth allowlist.
A local Vite build does not execute Vercel rewrites or verify its CDN behavior.
After deployment, test the proxy with authenticated requests and verify cache headers.

Use HTTPS on both provider domains. Verify HTTP redirects to HTTPS at the edge,
the proxy preserves Authorization, and responses to two users are never cache
hits. The backend has no cross-origin browser API policy; use the frontend URL.
The public `/api/health` proves the process is up, **not** that SQL is reachable,
migrations are applied, or a user is approved. Verify those separately with an
authorized `/api/me` request and a catalog request, without logging tokens.

### 4. OAuth domains, collection and friends

For the same Supabase project, the Google **provider callback** remains:
`https://PROJECT_REF.supabase.co/auth/v1/callback`. It is not the frontend URL.
Set Supabase's Site URL and allowlisted application redirect to the stable
`https://FRONTEND_DOMAIN/`. Google JavaScript origins use that origin without a
path/trailing slash. Keep the local origin/redirect only while needed for local
testing. Do not authorize arbitrary Vercel preview domains.

Activate the external collection secret/variables only after a direct manual
trigger succeeds. Use the existing [collection instructions](development.md#collection-on-render-free).
No workflow edit or extra token scope is needed for this preparation phase.

Before inviting friends, test owner and reader separately, direct API denial
without approval, session restoration, revocation and logout. Test installation
and Google PKCE on real Safari iPhone and Chrome Android, including return to the
same app storage context. Test collection after sleep. Desktop tests cannot
establish these mobile or hosted results.

## Backup, restore and deletion

From the repository root, for a separately chosen backup operation:

```bash
python3 scripts/backup_sqlite.py --source backend/data/news.db --destination backend/data/backups/CHOOSE_UNIQUE_NAME.db
```

Create the destination directory first if needed. The tool refuses an existing
destination and opens the source read-only. It uses SQLite's backup API, including
committed WAL data, then checks integrity and foreign keys. It writes mode 0600.
Keep backups outside Git, encrypted off-device as well as locally. Rehearse
restoration on a disposable copy, not by replacing the working database.

For PostgreSQL, use `pg_dump` of a compatible major version and a private libpq
connection service/password file. Do not put a credential URL on a command line.
After explicit backup authorization, from a private backup directory:

```bash
umask 077
pg_dump --dbname=service=tnr_operator --schema=tnr --format=custom --no-owner --no-acl --file=CHOOSE_UNIQUE_NAME.dump
pg_restore --list CHOOSE_UNIQUE_NAME.dump
```

Choose a nonexistent output filename (pg_dump can overwrite). Record its SHA-256,
server version and private per-table counts from the same quiet maintenance
window. For an approved restore rehearsal, select a new disposable database with
no `tnr` schema, then use `pg_restore --exit-on-error --single-transaction
--no-owner --no-acl --dbname=service=tnr_restore CHOOSE_UNIQUE_NAME.dump`.
Do not use `--clean` on a running database. Verify migration head, row contents,
counts, foreign keys and next sequence values, then reapply and check runtime
privileges. A schema dump excludes roles, passwords and Supabase Auth: it is not
a full Supabase-project recovery plan. A replacement Auth project requires a
separate identity-relinking plan; do not match accounts by unverified metadata.

Free Supabase has no managed daily backups to rely on. Before sharing the app,
choose a manual backup cadence (at least before each migration/transfer and
regularly during use), an off-device destination, retention and restore owner.
Keep a private deletion/revocation record and reapply it before restoring service.
Do not promise a recovery time until a restore rehearsal has succeeded.

For a verified reader's deletion request: first revoke access using
`python -m app.access revoke --subject VERIFIED_UUID`, confirm API denial, then
use the operator environment to run:

```bash
python -m app.access delete-reader --subject VERIFIED_UUID --confirm-subject VERIFIED_UUID
```

This irreversible operation requires an inactive reader, refuses the owner, and
removes their subscriptions, read states, and used email invitation. Shared sources/articles remain.
Cancel any separate pending invitations for that person from **Inviti**.
Delete the matching Supabase Auth user separately through an explicitly approved
cloud operation. Keep access revoked between the two steps. Re-invitation after
deletion creates a new profile; do not silently reconnect old backup data.
Explain backup retention to the requester. Owner removal or shutting down the
service needs a separate reviewed procedure. Before publication, review the
public privacy page, identify the administrator/contact channel to invitees,
and confirm it accurately describes the final providers and retention choices.

## Free-plan constraints (checked 2026-11-07)

| Service | Relevant current constraint | Operational effect |
| --- | --- | --- |
| Render Free | Sleeps after 15 minutes without inbound traffic; wake about a minute; 750 free instance hours/workspace/month | Cold starts are expected; no always-on scheduler guarantee |
| Render Free | Ephemeral filesystem; no persistent disk, shell or one-off jobs; resource/egress limits | PostgreSQL stays in Supabase; migrations/backup run from an operator machine |
| Vercel Hobby | Personal, noncommercial use; limited included usage; external proxy timeout 120 seconds | Suitable only while this remains a personal project; collection bypasses this proxy |
| Supabase Free | 500 MB database, 5 GB egress, 50,000 monthly active users, up to two active projects | Monitor database size and egress; article retention is not automatic |
| Supabase Free | Projects may pause after a week of inactivity; managed daily backups are not included | Verify project availability and keep independent backups |
| GitHub Actions | Scheduled jobs can be delayed; public-repository schedules disable after 60 days without activity | Check run history; hourly scheduling is not an uptime guarantee |

No retention job currently deletes old articles. Check database size before the
500 MB limit; any pruning policy must preserve agreed reading history and be
separately reviewed. Existing refresh limits remain: source cooldown starts at
30 seconds and increases on failures (maximum one hour); the external trigger
has a five-minute cooldown, no overlap, and bounded passes. Approved readers can
refresh only followed sources; only administrators can change catalog URLs.
The guarded downloader remains the outbound network boundary. Resource abuse
by approved users or repeated unauthenticated calls still requires monitoring;
this small deployment does not implement a distributed rate limiter.

Official references: [Vercel rewrites and caching](https://vercel.com/docs/routing/rewrites),
[proxy timeout](https://vercel.com/docs/errors/router_external_target_error),
[Vercel Hobby](https://vercel.com/docs/plans/hobby),
[Vercel shared source files](https://vercel.com/docs/monorepos/monorepo-faq),
[Render Free](https://render.com/docs/free),
[Render Blueprint](https://render.com/docs/blueprint-spec),
[Python version](https://render.com/docs/python-version),
[Render secret files](https://render.com/docs/configure-environment-variables#secret-files),
[Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Data API settings](https://supabase.com/docs/guides/api/disabling),
[Supabase pricing](https://supabase.com/pricing),
[Supabase backups](https://supabase.com/docs/guides/platform/backups),
[PostgreSQL restore](https://www.postgresql.org/docs/current/app-pgrestore.html),
[GitHub scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
