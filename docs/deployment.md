# Publication preparation

This guide describes the existing Supabase PostgreSQL deployment and its release
boundaries. Keep the private local `.env` and provider credentials out of Git.

## Reader usage release

Reader usage is implemented locally and awaits release. The full release below includes its migration and permission.
Keep frontend publication pending until the database and backend are ready.
During the authorized release, use the committed checkout and operator connection to apply Alembic revision `0012`.
Then run `backend/sql/enable_reader_usage.sql` with the operator connection.
This grants UPDATE only on `app_users.last_seen_at`. Identity, role and activation fields remain protected.
Deploy the backend commit, then verify `/api/me` and the administrator-only `/api/usage/readers` endpoint.
Keep native Vercel Git deployments disabled. A push runs checks only after the workflow transition below.
Publish the frontend only after backend verification. Keep schema migration commands out of API startup.
For rollback, restore the previous application versions before removing revision `0012`.

The feature stores one timestamp per profile, without event history or IP addresses.
`/api/me` updates it at most once per 15 minutes after authorization. Failed telemetry writes do not block access.
Automatic session renewals can update this value. It does not measure online presence or reading time.
The summary includes only currently authorized readers, excluding administrators and revoked profiles.
Read counts describe retained read marks, not lifetime reading totals. Profile creation is not necessarily the first visit.
Null timestamps mean no access recorded since activation. The private schema and existing database pool remain in use.

## Checks and manual releases from main

The repository separates automatic checks from production releases. Each push to `main` starts **CI checks**, without a deployment.
Use **Run workflow** on `main` to start either manual release. A successful CI run does not start a release.

| Workflow | Trigger | Scope | Template → GitHub workflow |
| --- | --- | --- | --- |
| **CI checks** | Push to `main` | Backend and frontend checks, with disposable local PostgreSQL databases and no production secrets | `deploy/ci.yml.example` → `.github/workflows/ci.yml` |
| **Release frontend only** | Manual | Frontend checks, production build, and Vercel publication | `deploy/release-frontend.yml.example` → `.github/workflows/release-frontend.yml` |
| **Release full** | Manual | Complete checks, Supabase migrations, Render deployment, and Vercel publication | `deploy/release.yml.example` → `.github/workflows/release.yml` |

Templates do not register workflows. Copy each template into its matching GitHub workflow with the web editor.
Local workflow edits have no effect on GitHub until you save them there.
The collection and digest workflows remain separate and retain their existing triggers.

### Choose a release

Use **Release frontend only** for UI changes compatible with the deployed API, such as CSS, text, or animation fixes.
This workflow installs only frontend dependencies. It does not run backend tests, connect to Supabase, or request a Render deployment.
It needs only the Vercel credentials and `TNR_RELEASE_ENABLED=true`.
Public Supabase settings remain part of the frontend build configuration retrieved from Vercel.

Before a frontend-only release, review all frontend changes since the last production deployment, not only the latest commit.
If any change requires a new API, database migration, or backend configuration, use **Release full**.
The workflow cannot determine API compatibility automatically. The frontend-only release does not deploy pending backend changes.

Use **Release full** for backend or database changes and for features that span both applications.
A separate backend-only workflow is not provided. The full release keeps migrations, backend verification, and frontend publication in one ordered procedure.
A backend-only workflow would add another release path without a current requirement.

### Checks and release order

**CI checks** runs backend lint, formatting, and tests against disposable local PostgreSQL databases.
It also runs frontend lint, TypeScript, tests, formatting, and build checks.
Every push starts checks, including documentation changes. A newer push can cancel an older CI run.
CI has a separate concurrency group and cannot cancel a production release.

**Release full** repeats the checks for its selected commit, then follows this order:

1. Check required configuration and build the production Vercel artifact.
2. Verify the Render target and reject a commit superseded by a newer `main` commit.
3. Apply Alembic migrations and the reviewed reader-usage permission on Supabase.
4. Deploy the same commit to Render and wait for its `live` status and `/api/health` response.
5. Publish the prebuilt frontend to Vercel Production.

**Release frontend only** repeats the frontend checks and builds the production Vercel artifact.
Immediately before publication, it rejects a commit superseded by a newer `main` commit.
Both release workflows restrict execution to `main` in the production repository.
Once a release starts production changes, a subsequent push does not cancel it or change its selected commit.

Both releases share the `production-release` concurrency group with `cancel-in-progress: false`.
Only one release can run at a time. The default queue permits one pending release.
A newer request can replace a pending request, including a request for the other release workflow.
Do not queue multiple releases or start provider deployments or migrations while a release runs.
A push starts only CI and does not join the release queue.

The workflows use standard Ubuntu runners. PostgreSQL services are temporary test databases, separate from Supabase.
No paid preview environment or Render one-off job is required. Provider quotas and Vercel Hobby eligibility still apply.

### One-time provider setup

Before the first release, verify the existing Supabase backup and its recovery procedure.
The command requires an existing application database at revision `0010` or later and an existing `tnr_app` role.
It supports the pending `0011` and `0012` migrations. It does not bootstrap roles or provision a new database.
Keep existing runtime grants from earlier releases. New permissions require explicit additions to the release implementation.

1. On Render, retain the existing GitHub repository and `main` branch.
2. Set Render **Auto-Deploy** to **Off**. The Action starts deployments through the API.
3. Keep the existing backend environment and CA secret file. Never add migration credentials to the web service.
4. On Vercel, disconnect the project's Git repository before pushing this transition.
5. Keep Vercel Root Directory `frontend` and include files outside that directory for `docs/assets` imports.
6. Keep Vercel Production environment variables and stable domains. Use **Automatic** for the ignored-build setting.

The committed `frontend/vercel.json` also sets `git.deploymentEnabled` to `false`.
Disconnecting Git first prevents an independent frontend release during the transition.
The Action links to the existing project by its organization and project IDs. Run Vercel commands from the repository root.

### GitHub configuration

Open the repository's **Settings → Secrets and variables → Actions**.
Add these values under **Secrets**, with **New repository secret**:

| Secret | Value |
| --- | --- |
| `TNR_MIGRATION_DATABASE_URL` | Operator session-pooler URL shown below |
| `TNR_SUPABASE_CA_CERT` | Complete PEM text of the project's CA certificate |
| `RENDER_API_KEY` | Render API token authorized to read the service and create/read deployments |
| `VERCEL_TOKEN` | Vercel token authorized for the existing project |

Use this URL shape, with the actual project reference, encoded password, and pooler hostname:

```text
postgresql+psycopg://postgres.PROJECT_REF:ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=verify-full
```

The release command writes the CA to a private temporary file and supplies `sslrootcert` itself.
It verifies the project reference, operator username, Supabase session-pooler hostname, port, database, and TLS mode before connecting.
Never copy a local `.env` into GitHub or put privileged credentials in `VITE_*` variables.

Add these values under **Variables**, with **New repository variable**:

| Variable | Value |
| --- | --- |
| `TNR_RELEASE_ENABLED` | `true` after provider setup is complete |
| `TNR_SUPABASE_PROJECT_REF` | Existing 20-character Supabase project reference |
| `RENDER_SERVICE_ID` | Existing backend service ID, starting with `srv-` |
| `TNR_BACKEND_URL` | Existing `https://SERVICE.onrender.com` origin, without `/api` |
| `VERCEL_ORG_ID` | Existing Vercel organization/team ID |
| `VERCEL_PROJECT_ID` | Existing Vercel project ID |

Use Vercel project/account settings for the IDs and token. Use Render service settings for its ID and account settings for its API token.
Production Supabase publishable settings remain in Vercel. `vercel pull` retrieves them for the build.
Secrets are supplied only to the steps that need them. Tests have no production database credentials.

### Install or update workflows through GitHub

The terminal token cannot create or update files under `.github/workflows/`.
Keep workflow changes out of terminal commits, including the modified `release.yml` and both new workflow files.
The `deploy/*.yml.example` templates are ordinary repository files and can use the normal commit and push procedure.

For the existing automatic release, complete this transition before the next terminal push:

1. Let any active production release finish. Inspect any uncertain remote deployment before continuing.
2. Open **Actions → Release production → … → Disable workflow** on GitHub.
3. Complete or verify the provider setup and GitHub configuration above.
4. Stage only the templates, documentation, and intended application changes. Do not use `git add .` or `git commit -a`.
5. Inspect `git diff --cached --name-only`. Confirm that it contains no `.github/workflows/` paths.
6. Commit the selected files with the normal terminal procedure.
7. Before web edits, save the local workflow copies with the command below. This keeps them out of the later pull.
8. Push the local commit with the normal token. The disabled old workflow must not deploy this push.
9. On GitHub, select `main` and edit the existing `.github/workflows/release.yml` file.
10. Replace its entire contents with `deploy/release.yml.example`. Commit the web edit directly to `main`.
11. Create `.github/workflows/ci.yml` from `deploy/ci.yml.example` with **Add file → Create new file**.
12. Create `.github/workflows/release-frontend.yml` from `deploy/release-frontend.yml.example` in the same way.
13. In Actions, enable the renamed **Release full** workflow if it remains disabled.
14. Confirm that **CI checks** passes for the latest `main` commit. Confirm that neither manual release starts automatically.
15. Run `git pull --ff-only` to receive the web commits. Keep unrelated local changes saved before the pull.
16. Compare each workflow with its template. Do not apply the saved workflow copies over the web commits.

Save only the three local workflow copies after the terminal commit, before the web edits:

```sh
git stash push --include-untracked -m "workflow copies before GitHub web installation" -- \
  .github/workflows/release.yml .github/workflows/ci.yml .github/workflows/release-frontend.yml
```

The stash is a local backup, not a commit to push. Keep its reported identity until the comparison succeeds.
After the pull, run these comparisons from the repository root:

```sh
cmp deploy/ci.yml.example .github/workflows/ci.yml
cmp deploy/release-frontend.yml.example .github/workflows/release-frontend.yml
cmp deploy/release.yml.example .github/workflows/release.yml
```

A successful comparison produces no output and returns exit code zero.
After all comparisons succeed, remove only that identified backup from the stash list.
For a new installation, create `release.yml` instead of editing it. The old-workflow disable step does not apply.
Always replace the existing release file during a transition. Leaving an old automatic release file active would preserve deployment on push.

Copy complete template contents without Markdown code fences. Keep each template and installed workflow identical.
For later updates, commit templates through the terminal and update the matching workflows through the web editor.
Use the same local-backup and pull procedure when local workflow edits are present.

### Start a release

1. Open **Actions** after CI succeeds on the intended `main` commit.
2. Select **Release frontend only** or **Release full**, according to the compatibility rules above.
3. Select **Run workflow**, choose `main`, and start the workflow.
4. Monitor that workflow through completion before starting another release.
5. After publication, verify login and the affected application screens.
6. For a full release, also verify `/api/me` and the administrator reader-usage screen when applicable.

The **Run workflow** button appears after a manual workflow exists on the default branch.
Incomplete configuration stops a release before publication or production database changes.
Correct the configuration before a new manual attempt. A failed CI run never starts either release.

### Failures and compatibility

All stages stop on failure. A successful database stage remains committed if a later hosting stage fails.
No stage performs an automatic downgrade or database restore. Inspect remote state before rerunning an uncertain operation.
The Render client sends one deploy request, then polls its returned ID. It verifies both the commit SHA and process health.
Process health does not prove authenticated database access. The first release still needs the application checks listed above.
If Render times out, check its dashboard before retrying: an accepted deployment can continue after the Action stops.

The database stage uses one transaction for migrations and the reviewed column-level grant.
It takes an advisory transaction lock, with a ten-second lock timeout and a two-minute timeout per SQL statement.
An exception rolls back that transaction. Rerunning after success applies no duplicate migration and repeats the idempotent permission grant.
Future migrations must support this transaction model. Migrations that require autocommit need a separate release design.

Keep migrations compatible with the currently deployed backend and active collection/digest jobs.
Add columns or endpoints first. Remove old columns or endpoints in a later release after their callers stop using them.
The pipeline cannot determine whether arbitrary SQL preserves application compatibility.
To stop future production writes, set `TNR_RELEASE_ENABLED` to `false`. This does not stop an already running release.

References: [GitHub manual workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow),
[Render deployment API](https://api-docs.render.com/reference/create-deploy),
[Vercel with GitHub Actions](https://vercel.com/kb/guide/how-can-i-use-github-actions-with-vercel),
and [GitHub workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

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
| `frontend/vercel.json` | Vercel configuration for the verified Render hostname; native Git deployments disabled for ordered releases |
| `backend/sql/create_app_role.sql` | One-time, separately authorized database-role setup after migrations |
| `backend/sql/check_app_role.sql` | Read-only inspection of role and schema access |
| `frontend/public/privacy.html` | Public explanation of authentication, personal data and deletion requests |

The `.example` templates are not active hosting configuration files.
`frontend/vercel.json` will apply when Vercel builds this frontend. Its presence
does not mean that a frontend deployment exists. Do not deploy without separate
approval. The current local head is `0012`.
For an existing `0006` deployment, use the [AI brief rollout](ai-briefs.md#coordinated-publication-plan--not-executed).
For an existing `0005` deployment, follow the [source proposal rollout](deployment.md#source-proposal-rollout).
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
| `TNR_MIGRATION_DATABASE_URL` | Operator environment or release Action secret | Privileged connection for Alembic | **Secret**; forbidden in the production web service |

Omit `TNR_LOCAL_USER_ID`, `VITE_LOCAL_MODE`, and operator credentials from hosting.
Keep feed limits at their existing defaults unless measured results require a
change. Use a separate operator shell/environment for migrations and access
commands. The running application must use only the restricted `tnr_app` URL.

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

Read [PostgreSQL](deployment.md#postgresql-configuration). Record the project, server version, region,
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
- `app_users` permits SELECT and reader-only INSERT, plus UPDATE on `last_seen_at` only after revision `0012` and its explicit grant.
  Seven data tables permit SELECT/INSERT/UPDATE/DELETE. `alembic_version` has no runtime access. Sequences permit USAGE only.
- `anon`, `authenticated` and `service_role` have no `tnr` schema/table access.
- `tnr` is not in Data API exposed schemas. Disable the Data API if unused by
  other project applications; this app uses direct SQL and Supabase Auth.

Check the grants again after each migration. There are no default grants to new
tables. RLS does not protect a privileged SQL connection. The backend enforces
per-user access; `tnr_app` is not a per-user database identity.

### 2. Completed data transition

Application data now resides in Supabase PostgreSQL. The retired embedded-database transfer utilities are not part of the active codebase. Keep verified PostgreSQL backups and use the standard release path for future migrations.

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

#### Ordered deployment from `main`

Use [Checks and manual releases from main](#checks-and-manual-releases-from-main) for the existing installation.
Native Vercel Git deployments are disabled in the repository. **Release full** publishes Vercel after Supabase and Render succeed.
**Release frontend only** publishes compatible UI changes without those backend stages.
These manual workflows replace the earlier deployment on push.

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
template, but initial Blueprint creation still deploys. **Release full** starts later backend deployments through the API.

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

Use `pg_dump` of a compatible major version and a private libpq
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

## Shared AI briefs — local implementation

The [AI release plan](ai-briefs.md#coordinated-publication-plan--not-executed) coordinates backup, migrations through `0010`, and minimal runtime grants.
No remote migration, grant, key configuration, deployment, or activation is part of the local Gemini phase.
The backend and workflow stay disabled. `TNR_AI_BUDGET_RISK_ACCEPTED` also defaults to false.
A later authorized release must verify the remote revision, accepted budget limitations, privacy, and billing state before enabling generation.
Backups must preserve the monthly money ledger. Do not reset, discard, or restore
an older ledger to repeat an uncertain request.

## PostgreSQL configuration

Supabase PostgreSQL is the only application database. Tests use disposable local
PostgreSQL databases and must never connect to Supabase.

Database support includes the [multiuser data model and backend permissions](authentication.md#user-roles-and-personal-data).
The backend supports [Supabase token verification and access approval](authentication.md).
Frontend login is implemented. Cloud configuration and deployment require separate authorization.
Keep the backend on loopback with one process and one worker.

### Connection configuration

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

### Migrations and the private schema

PostgreSQL application tables and `alembic_version` live in the fixed `tnr` schema.
Connections set `search_path` to `tnr` and the session timezone to UTC.
They do not fall back to `public` for application tables.
Alembic creates the namespace in the migration transaction before it runs the unchanged revision `0001`.
Revision `0002` adapts PostgreSQL types and constraints.
Revision `0003` adds application users and personal data. It preserves the reserved local owner's existing read flags.
Revision `0004` adds a unique identity link on the existing private user table. It does not grant new privileges.
Revision `0005` adds `reader_invitations` and reader-only INSERT policies on `app_users`, without changing existing profiles.
It revokes inherited Data API grants on the new table. Runtime grants remain a separate operator operation.

Set `TNR_MIGRATION_DATABASE_URL` to an owner connection when the application uses a restricted database role.
Alembic and the operator access commands use this URL for explicit database operations. If unset, it uses `TNR_DATABASE_URL`.
Use a direct connection for migrations where reachable. Session pooling is the IPv4 alternative.
Both connections must target the same database. The API never reads the migration URL to connect, creates tables, or applies migrations.

For an authorized target, run these commands from `backend/`:

```sh
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic check
```

The expected revision is `0012 (head)`. Use the release Action for the configured production target, or obtain authorization for a manual operation.
This implementation does not move application tables from an existing PostgreSQL `public` schema.
Do not use it to stamp or adopt an unrelated database. Review that case separately.

Downgrades are for disposable databases. A downgrade to `0001` can reject long Unicode keys that do not fit a B-tree.
Downgrading `0003` discards user accounts and subscriptions, and retains only the reserved owner's read flags in the single-user schema.
PostgreSQL rolls back that migration transaction. A downgrade to `base` removes application data but retains the private namespace.

### Data API and database privileges

Reviewed setup and inspection SQL is in `backend/sql/`. See the
[publication guide](deployment.md#1-database-configuration-and-schema) for the
separate migration, role-setup and data-transfer approval gates, and the
[backup/restore procedure](deployment.md#backup-restore-and-deletion).

Keep `tnr` out of the Supabase Data API's exposed schemas. If no feature needs the Data API, disable it during an authorized setup.
Supabase Auth does not require exposing these application tables.
Revision `0002` revokes schema, table, and sequence privileges from `PUBLIC` and existing `anon`, `authenticated`, and `service_role` roles.
Revision `0003` also revokes table privileges on the new personal tables, including inherited default grants to these API roles.
It does not change the `public`, `auth`, or `storage` schemas or create cloud roles.
The schema boundary remains necessary for future tables, including tables that inherit broad project default grants.

Use a separate login role for the backend before deployment. It needs `USAGE` on `tnr` and `SELECT, INSERT` on `app_users`.
It needs CRUD on catalog, collection, subscription, read-state, and invitation tables, plus `USAGE` on their sequences.
The API can create only active readers through explicit invitations. Existing role and access changes remain privileged operator operations.
It must not own the schema or tables, inherit privileged roles, or have `SUPERUSER`, `BYPASSRLS`, `CREATEROLE`, or `CREATEDB` privileges.
Keep schema ownership and DDL permissions on the migration connection.
Provisioning roles, passwords, grants, and Data API settings remains an explicit cloud-setup task.
Do not run the application as the supplied Supabase `postgres` owner in a public deployment.

RLS on `app_users` permits runtime reads and inserts of active readers with a matching consumed invitation.
The runtime role cannot insert administrators or delete profiles. It can update only `last_seen_at`, not identity or access fields.
It cannot change these policies.
These policies do not isolate individual users. API authorization remains the per-user access boundary.
For an existing runtime role, review `backend/sql/enable_reader_invitations.sql` after migration `0005`.
Both operations require separate authorization for a remote database.
Owners and roles with `BYPASSRLS` can bypass RLS. SQL connections do not acquire end-user authorization from Supabase Auth automatically.
FastAPI verifies Supabase tokens and checks approved, active profiles and application roles.
Its alternative local identity adapter is not authentication.
Real Google login validation and authorized cloud configuration remain necessary before public deployment.

See [Supabase Data API security](https://supabase.com/docs/guides/api/securing-your-api) and
[PostgreSQL row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

## Source proposal rollout

This manual procedure applies to older installations that lack the source-proposal schema and runtime grants.
For the configured installation at `0010` or later, use [Checks and manual releases from main](#checks-and-manual-releases-from-main).

1. Review the local diff and tests. Authorize commit, push, migration, grants, and deployment separately when ready.
2. Record the remote revision and current grants with a read-only operator check. Confirm the existing target and backups.
3. Obtain and verify a recoverable database backup. Preserve existing identities, invitations, subscriptions, and reading states.
4. Coordinate collector inactivity and apply only missing migrations for the reviewed release with the operator connection.
   Source proposals require `0006`; the current release also includes `0007 → 0008 → 0009 → 0010`.
   Follow the [AI release procedure](ai-briefs.md#coordinated-publication-plan--not-executed) for those revisions, keeping AI disabled.
5. Apply `backend/sql/enable_source_proposals.sql` and any missing grants required by the reviewed release, then inspect `backend/sql/check_app_role.sql` results.
6. Confirm `tnr_app` has SELECT/INSERT/UPDATE on proposals and USAGE on its sequence, without DELETE or role-management privileges.
7. Confirm PUBLIC, anon, authenticated, and service_role have no access to the new table or sequence.
8. Deploy the backend manually on Render, using the reviewed revision. Verify health and authorized proposal endpoints.
   Use that revision for operator access commands as well; do not run an old `app.access` during rollout.
9. Publish the frontend on Vercel only after backend compatibility is confirmed.
10. Check reader isolation, approval, cancellation, both languages, counter refresh, and the installed-app return path.

For older installations with native Vercel Git deployment, a push can publish the frontend before the backend is ready.
Pause native Vercel deployments before a combined manual release.
Do not enable the new frontend while its API is unavailable.
Continue to verify the expected commit and deployment status after each push.
Never initialize or reimport the populated remote database.

For rollback, revert application releases while keeping the additive table and grants for investigation.
Do not downgrade the production database: dropping `source_proposals` destroys proposal history.
The transfer utilities require the current release revision (`0010`) at both ends and include proposals and their sequence.
They remain operator-only tools, not part of this rollout. Do not run them against the existing populated Supabase database.

### RSS news refresh rollout — not executed

Stop collection traffic before the coordinated backend release. Apply revision `0010` with the existing migration connection.
This revision adds `sources.last_attempt_at` and backfills attempt times from collection history. It does not delete data or change retention.
Existing table-level application grants cover the new column. No new role or cloud service is required.
Deploy the matching backend and frontend together after migration. Keep one backend worker.
Verify approved-reader scope, revoked access, cooldowns, HTTP 304, and the mobile gesture after release.
Check cold starts and a disconnected response on Render separately. Local tests do not measure those conditions.
Do not change the operator trigger secret, hourly workflows, or Gemini activation for this release.
