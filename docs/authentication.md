# Authentication and access approval

The backend verifies Supabase access tokens and accepts only explicitly approved application users.
The frontend provides Google sign-in, browser session recovery, logout, and personal source selection.
Google provider setup and deployment still require separate authorization. Installing the code does not configure cloud accounts.

Use the [local Google login procedure](authentication.md#local-google-login) to configure and verify a real Supabase session.

## Identity and permission boundary

The browser must send a Supabase **access token** in `Authorization: Bearer <access-token>`.
A Google ID token, Supabase API key, database password, or service-role token is not an application access token.
The backend does not accept tokens from URLs, cookies, or user-selection headers.

The verifier checks the signature, exact issuer, `authenticated` audience, expiry, issue time, session UUID, and subject UUID.
It accepts ES256 and RS256 signatures from the configured project's public JWKS endpoint.
It rejects anonymous users and tokens whose database role is not `authenticated`.
This token role is not the application's `admin` or `reader` role.
The application loads its role and active status from `app_users` on every request.
Neither user-editable metadata nor Google test-user lists grant application access.
An email grants access only through an explicit administrator invitation and the verified Google identity check below.

Revision `0004` adds a nullable, unique `supabase_subject` to `app_users`.
Existing profiles and personal data keep their IDs. No profile receives an identity automatically.
The backend looks up the verified subject through this link. It never treats a JWT subject as an application profile ID.
No HTTP endpoint changes existing roles or links the reserved administrator.
Revision `0005` adds administrator email invitations. A valid invitation creates one active reader at first authenticated access.
An unapproved Supabase user receives `403` and creates no application data.

The application database supports one Supabase Auth project.
Do not change `TNR_SUPABASE_URL` to another project while keeping existing identity links without a separate migration plan.
PostgreSQL stores application identities and permissions in the private `tnr` schema.
No foreign key to the remote `auth.users` table is required.

The optional `POST /api/internal/collect` is a machine-only exception with a separate bearer secret.
It can only scan existing due sources; it cannot read personal data, approve users, or change the catalog.
User access tokens do not authorize this endpoint, and its secret does not authorize user endpoints.
It returns `404` while unconfigured. See [external collection](development.md#collection-on-render-free) for activation and rotation.

## Configuration

Set these values in the private root `.env` for local integration testing, after cloud setup is authorized:

```dotenv
TNR_SUPABASE_URL=https://PROJECT_REF.supabase.co
TNR_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_WITH_PUBLIC_KEY
VITE_SUPABASE_URL=https://PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_WITH_PUBLIC_KEY
```

Both URLs must identify the same project. Only the `VITE_*` values enter the browser build.
Use the project's public publishable key, never a secret key, service-role key, or database password.
The frontend accepts `sb_publishable_` keys; legacy JWT API keys are not supported by this configuration.
The backend verifies JWT signatures without an API key.
Email invitations additionally require `TNR_SUPABASE_PUBLISHABLE_KEY` to verify the Google identity through Supabase Auth.
Use the same public key as the frontend. Existing approved users do not require this additional request.
Restart affected local servers after environment changes. Rebuild production frontend assets after frontend configuration changes.

Remove `TNR_LOCAL_USER_ID` and `VITE_LOCAL_MODE` when you enable Supabase authentication.
Setting both causes a configuration error. Failed bearer authentication never falls back to a local administrator.
Keep `TNR_LOCAL_USER_ID` only for loopback development without Supabase.
When neither setting exists, data endpoints return `401`.
Health and optional API documentation remain available.

The URL must be an HTTPS origin, without a path, query, fragment, credentials, or a nonstandard port.
The issuer is `<origin>/auth/v1`. Public keys come only from `<issuer>/.well-known/jwks.json`.
Token headers cannot change the key URL. HTTPS certificate verification remains enabled, and JWKS redirects are rejected.
Tokens are limited to 16,384 characters. Encoded headers are limited to 2,048 characters before JSON parsing or key retrieval.
The backend does not need an Auth secret, service-role key, or publishable key for this verification.
Never place database credentials or privileged keys in frontend configuration.

This implementation requires asymmetric Supabase signing keys: ES256 or RS256.
Legacy HS256 tokens are rejected. Inspect the project's signing-key configuration during the later authorized cloud setup.
Do not rotate keys or copy a JWT signing secret merely to run local tests.

The verifier caches the key set for five minutes, with no permanent per-key cache.
An unknown key can trigger a refresh after a 30-second cooldown.
A new signing key can therefore take up to 30 seconds to become available after a recent fetch.
Network operations have a five-second timeout. A failed fetch causes a ten-second retry backoff.
An unavailable key service returns `503`, with `Retry-After: 10`.
Invalid or missing tokens return `401`. Unknown or inactive application users return `403`.
Supabase can also cache its JWKS response upstream. Coordinate key rotation with the official signing-key guidance.

Apply migration `0005` explicitly to an authorized database before you enable the API or run access commands.
The API and access commands never apply migrations automatically.
Back up existing data before migration. Supabase migrations still require separate owner authorization.
Downgrading to `0003` removes identity links and blocks Supabase access, but preserves profiles, subscriptions, and read states.

## Invite friends by email

This feature requires migration `0005`, the runtime grants, and the backend public key described above.
Source code alone does not activate it on an existing deployment.

1. Sign in as the administrator.
2. Open **Inviti**.
3. Enter the person's display name and their Google account email.
4. Select **Salva invito**.
5. Share the application link with that person through your usual channel.

A pending invitation appears as **In attesa**. Select **Annulla invito** to remove it before use.
At first login, the backend creates an active reader and marks the invitation **Utilizzato**.
The reader starts with no subscriptions or read states. The existing source-selection screen guides them.
If the person already sees **Accesso riservato**, they can select **Verifica di nuovo** after you save the invitation.

The list contains invitations, not all existing users. It cannot change roles or reactivate a revoked account.
Used invitations cannot be cancelled through HTTP. Use the operator commands below for revocation and reactivation.
Adding an invitation for an existing profile does not change that profile or consume the invitation.
Cancel such unused invitations when they are unnecessary.

Email matching ignores case and surrounding spaces. It accepts ASCII email addresses and preserves dots and plus aliases.
Use the Google account email itself, not an alternate forwarding address.
Duplicate emails return `409`. Names, emails, and acceptance timestamps are visible only to administrators through these routes.
`GET/POST /api/invitations` and `DELETE /api/invitations/{id}` require an active administrator.
The API accepts no role, subject, or acceptance fields in invitation input.

For an unknown JWT subject, the backend first checks for a pending email invitation.
It then requests the current user from the fixed Supabase `/auth/v1/user` endpoint with that bearer token and public key.
The response must identify the same subject and confirmed email, with a matching verified Google identity.
User-editable `user_metadata` is not evidence of email ownership. An unconfirmed, different, or non-Google identity cannot claim the invitation.
A failed upstream lookup leaves the invitation pending. Temporary failures return `503` with a retry delay.

The claim and reader insert share one transaction. Concurrent claims create at most one profile.
A concurrent cancellation prevents a later claim. Existing profile links and inactive status take precedence over invitations.
A used invitation cannot create another account or restore a deleted profile automatically.
The operator `delete-reader` command also removes that reader's used invitation and email.
Cancel unrelated pending invitations separately when processing a deletion request.

Before production rollout, run the [isolated PostgreSQL tests](development.md#isolated-postgresql-tests), including the runtime role checks.
For an existing production deployment, prepare a fresh backup and obtain authorization before remote changes.
Apply migration `0005` with the operator connection. Review and apply `backend/sql/enable_reader_invitations.sql` separately.
Set the public backend key on Render, then deploy and verify the backend before the frontend.
Keep automatic deployment disabled unless separately authorized. See [database privileges](deployment.md#data-api-and-database-privileges).

Reference: Supabase [server-verified user retrieval](https://supabase.com/docs/reference/javascript/auth-getuser)
and [user identities](https://supabase.com/docs/guides/auth/identities).

## Approve the administrator and friends

Link the administrator by verified Supabase UUID with the operator command below.
For friends, use administrator email invitations before their first login, or the existing operator approval after login.
Neither method sends email messages.
Until approval, the frontend shows **Accesso riservato**. After approval, the person can select **Verifica di nuovo** without signing in again.
A Supabase account alone does not mean that the person is an approved application user.

Before provisioning, inspect the correct Supabase project's user record in its authenticated dashboard.
Confirm the person's identity, Google identity, and user UUID through a trusted channel.
Use the Supabase user UUID, not a Google subject, application profile UUID, email, or UUID supplied without verification.
Do not paste access tokens or private identity lists into Git, issue reports, or shared logs.

Run the following commands from `backend/` against the intended application database.
Replace the uppercase placeholders with verified UUIDs. These examples are not ready to run.
The commands use `TNR_MIGRATION_DATABASE_URL` when set, otherwise `TNR_DATABASE_URL`.
They need privileged write access to `app_users`. The runtime role can update only `last_seen_at`, not identity or access fields.
It cannot delete profiles.
Its PostgreSQL insert permission is limited by the reader-only RLS policy from migration `0005`.
An operator command changes its configured database, so remote execution requires explicit authorization.

Link your verified account to the reserved administrator:

```sh
.venv/bin/python -m app.access link-owner --subject OWNER_SUPABASE_USER_UUID
```

This preserves your existing subscriptions, read states, role, and active status.
Repeating the same link is harmless. Linking a different subject fails without replacing the current link.
A subject already assigned to another profile cannot also become the owner.
There is no first-registration administrator rule or automatic account merge.

Approve a friend as an active reader:

```sh
.venv/bin/python -m app.access invite --subject FRIEND_SUPABASE_USER_UUID --name "Friend"
```

A new reader starts without subscriptions or copied read states.
Repeated approval preserves the existing profile and does not undo a revocation.
The command cannot grant administrator status.

Revoke access:

```sh
.venv/bin/python -m app.access revoke --subject FRIEND_SUPABASE_USER_UUID
```

The next authorization check rejects the user's requests, including requests with an unexpired token.
A request already authorized and running can finish. Revocation preserves personal data.
Source proposal decisions and operator access changes share a transaction lock:
an approval that holds the lock finishes before revocation; an approval waiting behind
revocation rechecks access and refuses the revoked proposer. Use the current release
for operator commands as well as the API; direct SQL updates bypass this coordination.
This operation can also disable the owner in an emergency. It does not terminate Supabase sessions or delete cloud accounts.

Restore access explicitly:

```sh
.venv/bin/python -m app.access activate --subject FRIEND_SUPABASE_USER_UUID
```

Activation preserves the previous role and personal data. It does not provision an unknown identity.
Recovery from an incorrect owner link needs a separate reviewed database operation.
No command silently replaces or transfers an identity link.

## Browser sessions and source selection

For permanent removal of an inactive reader, see the
[deletion procedure](deployment.md#backup-restore-and-deletion). The operator-only
`delete-reader` command requires the verified subject twice, refuses the owner,
and removes the reader's personal rows. Revocation alone keeps those rows.
Supabase Auth deletion remains a separate cloud operation.

The frontend uses `@supabase/supabase-js` with OAuth authorization code flow and PKCE.
The Google button starts `signInWithOAuth` with the current origin and pathname as the return URL.
It does not accept a return URL from query parameters. Callback codes are exchanged once and removed from browser history.
Provider error descriptions are not displayed or logged by application code. The page uses a no-referrer policy.

The SDK stores and refreshes the session in browser storage. Application requests obtain the current access token
and send it only to same-origin `/api` endpoints. The frontend does not access database tables through Supabase's Data API.
`GET /api/me` confirms application access and supplies the role before catalog or article requests begin.
Only administrators see **Catalogo** and **Categorie**. Backend permission checks remain authoritative.
An expired session returns to login; denied access shows the approval screen; connection failures offer a retry.
Logout or account changes abort pending requests and remove the previous account's interface state.
The frontend calls `signOut({ scope: 'local' })`: logout affects this browser, not every device.

Readers without subscriptions see the shared catalog with enabled sources proposed initially.
Nothing is saved until they confirm. **Non ora** skips the choice; an empty profile sees the proposal again on a later page load.
Existing subscriptions are never replaced by the initial proposal. **Le mie fonti** lets each person follow or unfollow sources later.
Unfollowing preserves personal read states. A failed multi-source save can be retried; repeated subscriptions are idempotent.
New catalog entries are not followed automatically.

For account-free loopback development, set `TNR_LOCAL_USER_ID` and `VITE_LOCAL_MODE=true`, with all Supabase settings absent.
The frontend local mode works only in a development build on a loopback hostname. A production build rejects it.
Do not expose this mode through a public proxy. See [local development](development.md).

### Installed web app sessions

Installation retains the same Supabase OAuth/PKCE flow. Do not assume that a browser tab and an installed app share storage.
The callback must reach the context that holds the PKCE verifier. Do not copy authorization URLs between windows.
On each supported iPhone and Android version, start login from the installed app and complete Google's consent flow.
Check that the callback returns to a usable signed-in app, then close and reopen it to check session recovery.
Check token renewal, logout, a second account, and denied or revoked access there too.
If the callback opens in a different context and login fails, record the device, OS, and browser versions.
Do not treat login in a browser tab as proof of installed-app compatibility.
See [installation instructions](development.md#install-the-web-app). Real-device OAuth validation remains required before release.

## Google setup and remaining limits

JWT verification does not query `auth.sessions` on every request.
A Supabase logout or session revocation does not invalidate an already issued access token before its expiry.
For immediate application access removal, use the local access-revocation command against the application database.
The frontend clears its application state on logout and uses the SDK for session storage and renewal.

Configure Google as the intended sign-in provider during the authorized cloud setup.
Disable unused sign-in methods and anonymous sign-in there.
The backend verifies Supabase user sessions. It does not infer the current OAuth provider from user-editable metadata.
In Google Cloud, the OAuth redirect URI is the Supabase callback, `https://PROJECT_REF.supabase.co/auth/v1/callback`.
In Supabase, configure the application Site URL and allow the exact frontend return URLs.
For local testing with the default port, the return URL is `http://127.0.0.1:5173/`.
Google origins, callback URIs, application redirects, and CORS still need validation with the actual environments.
The current frontend expects same-origin `/api`; production routing is part of the deployment step.
Google test-user settings do not replace the application's approval list.

The Google Identity Services button was evaluated. This version uses the HTML button option from Google's branding guide,
including its provided multicolor mark, with Supabase's OAuth/PKCE flow.
It does not load the Google Identity Services script or use a direct Google ID-token flow, which would require separate client-ID and nonce handling.
The official branding reference is listed below. No third-party font request is added.

## Verification

Tests use generated EC/RSA signatures, mocked JWKS HTTP responses, and real Alembic migrations on disposable databases.
They check malformed, expired, forged, wrong-project, wrong-audience, anonymous, and privileged-role tokens.
They also check key rotation, cache behavior, upstream failure, owner preservation, explicit approval, personal isolation, and revocation.
Frontend tests mock the SDK and HTTP to check callback handling, session recovery, refresh, logout, approval,
account isolation, administrative controls, and subscription changes, including interrupted saves.
The tests do not use the personal Supabase project or live news services.

Live identity, hosted connectivity, and deployed session checks remain separate from the simulated suite.

## Official references

- [Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts)
- [Supabase JWT claims](https://supabase.com/docs/guides/auth/jwt-fields)
- [Supabase signing keys](https://supabase.com/docs/guides/auth/signing-keys)
- [Supabase sessions](https://supabase.com/docs/guides/auth/sessions)
- [Google sign-in through Supabase](https://supabase.com/docs/guides/auth/social-sign-in/auth-google)
- [Supabase PKCE flow](https://supabase.com/docs/guides/auth/sessions/pkce-flow)
- [Supabase session events](https://supabase.com/docs/reference/javascript/auth-onauthstatechange)
- [Supabase logout](https://supabase.com/docs/reference/javascript/auth-signout)
- [Google button branding and HTML option](https://developers.google.com/identity/branding-guidelines)
- [PyJWT verification and key caching](https://pyjwt.readthedocs.io/en/latest/api.html)

## Source proposals

See [source proposal behavior and API](architecture.md#source-proposals) and
[publication and grants](deployment.md#source-proposal-rollout).

## Shared hourly AI digest — local implementation

[Digest reads](ai-briefs.md#api-authorization-and-durable-admission) use approved-user Google/Supabase authorization and respect revocation.
The former category routes have been removed and return `404` for every user.
The scheduled operator endpoint uses a separate trigger credential and exposes only operational status.
That credential cannot read user data or impersonate a reader. The future Gemini Developer API key is backend-only.
Only the direct Google API is supported.
Roles, invitations, approvals, and revocations are unchanged. Generation and budget-risk acceptance remain disabled by default.

## User roles and personal data

### Roles and access

| Operation | Active reader | Active administrator |
| --- | --- | --- |
| Browse sources, categories, and shared articles | Yes | Yes |
| Follow or unfollow a source | Own subscriptions only | Own subscriptions only |
| Set an article's read status | Own state only | Own state only |
| Create, change, disable, or delete sources | No | Yes |
| Create, change, assign, or delete categories | No | Yes |
| Refresh a source | Followed and globally enabled sources | Any globally enabled source |
| View shared collection history | Yes | Yes |
| Create, list, or cancel pending reader invitations | No | Yes |
| Change existing application accounts or roles through HTTP | No endpoint | No endpoint |

Unknown and inactive users cannot access data endpoints. New application records default to `reader` and inactive.
Activation requires operator approval or an administrator email invitation claimed by a verified Google identity. No first-registration administrator rule exists.
The backend loads role and active status from the application database on every request.
It does not accept these values from client JSON, query parameters, headers, or Supabase user metadata.

The automatic collector remains shared and processes enabled sources even when nobody follows them.
Manual refreshes share the existing cooldown and collection lock across users.
The authorization lookup releases its transaction before a download starts. Use one backend process and one worker per database.

### Personal behavior

`GET /api/articles` defaults to followed sources. `subscribed_only=false` includes the full shared archive.
A subscription is a personal feed choice, not an access grant to an otherwise private article.
Existing category, source, search, read-state, ordering, and pagination filters still combine.
Every response and read-state filter uses the current user's state, including full-archive requests.

An `article_read_states` row means read. A missing row means unread.
Marking an article unread deletes only the current user's state row.
Unfollowing a source leaves article read states intact. Following it again restores the same personal reading history.
New readers receive no subscriptions or copied read states. The frontend proposes enabled catalog sources and saves only confirmed choices.
Creating or importing a catalog source does not subscribe other users or the administrator automatically.

Disabling a source stops collection globally but preserves existing articles, subscriptions, and read states.
Deleting a category leaves its sources uncategorized. Deleting a source removes its articles, history, subscriptions, and associated read states.
Deleting an application user removes only that user's subscriptions and read states. It does not delete shared content.
Prefer source deactivation when permanent deletion is unnecessary.

### Schema and migration

The PostgreSQL models include:

- `app_users`: UUID identity, display name, `admin`/`reader` role, active status, and creation timestamp.
- `subscriptions`: composite primary key `(user_id, source_id)` and creation timestamp.
- `article_read_states`: composite primary key `(user_id, article_id)` and read timestamp.
- `reader_invitations`: unique normalized email, display name, inviting administrator, and one-time acceptance state.

Foreign keys cascade personal data cleanup. Indexes on `source_id` and `article_id` support reverse lookups and deletion.
The application uses conflict-safe inserts for repeated subscription and read requests.
Preliminary reads finish before conflict-safe personal writes.

Revision `0003` leaves shared catalog IDs, article data, category edits, and collection history intact.
It explicitly creates the reserved local owner `00000000-0000-0000-0000-000000000001` as an active administrator.
It follows all existing sources for that owner, including disabled sources, and copies only existing true read flags to personal rows.
The migration then removes `articles.is_read`. It does not copy those flags to future readers.
Timestamps on migrated subscriptions and read states record the migration time, not the original unknown action time.
Repeated upgrades do not restore subscriptions the owner subsequently removed.

The reserved owner initially has no Google account or Supabase identity attached.
Revision `0004` adds identity links. The operator must explicitly link the owner's verified Supabase UUID to this profile.
See [authentication and access approval](authentication.md). Do not assign this profile to the first person who signs in.

The new PostgreSQL tables remain in `tnr`. The migration revokes their privileges from `PUBLIC` and existing Data API roles.
No Supabase project or personal database is changed merely by installing the code.

Apply migrations explicitly with the [development commands](development.md#initialize-the-database).
Back up Supabase PostgreSQL before upgrading existing data. Do not apply migrations while the backend is running.
Downgrading to `0002` is destructive: it discards profiles and subscriptions, and restores only the reserved owner's flags to articles.
Use downgrade tests only on disposable databases.

## Local Google login

This procedure connects the existing local application to hosted Supabase Auth.
Application data and authentication both remain in the configured Supabase project.
It does not deploy the application.

Complete each checkpoint before the next section. Cloud changes require the owner's authorization.
See [authentication](authentication.md) for identity checks and operator-command behavior.

### 1. Check the local state

1. Check the branch, working tree, and listeners on ports `8000` and `5173`.
2. Confirm that each listener belongs to this repository before you stop or restart it.
3. Check the configured database type without printing credentials.
4. Check that the database schema matches this release, using the [migration procedure](development.md#initialize-the-database).
5. Record the owner's profile ID, role, active status, identity-link status, subscriptions, and read-state counts privately.

The reserved owner ID is `00000000-0000-0000-0000-000000000001`.
An existing identity link must match the intended Supabase account. Do not replace a conflicting link.
The access commands use `TNR_MIGRATION_DATABASE_URL` when present, otherwise `TNR_DATABASE_URL`.
Both the API and operator commands must target the same Supabase database for this procedure.

**Checkpoint:** The database and owner are identified. No migration or replacement database is necessary.

### 2. Identify the Supabase project and current key

1. Open the intended project in the Supabase dashboard.
2. Copy its Project URL from the project connection or API settings.
3. Open **JWT Keys** in the project settings.
4. Inspect the **CURRENT** key's algorithm.

`ECC (P-256)` corresponds to ES256. RSA signing with RS256 is also supported.
HS256 is not supported. If the current key uses HS256, stop before changing keys.
Prepare a separate migration decision that accounts for other applications using the project.

The public endpoint is `https://PROJECT_REF.supabase.co/auth/v1/.well-known/jwks.json`.
A compatible key in this response alone does not prove that Supabase currently signs tokens with it.
The response can include standby or previously used keys.

**Checkpoint:** The selected project has a compatible current key and an accessible public key set.

### 3. Configure Google and Supabase manually

Use one browser origin throughout the test: `http://127.0.0.1:5173/`.
`localhost` and `127.0.0.1` have separate browser storage, including the PKCE verifier.
Do not change the hostname between login and callback.

Replace `PROJECT_REF` below with the verified project reference.

| Setting | Value | Purpose |
| --- | --- | --- |
| Google OAuth client type | Web application | Supabase completes the Google server callback |
| Google authorized JavaScript origin | `http://127.0.0.1:5173` | Frontend origin, without a path |
| Google authorized redirect URI | `https://PROJECT_REF.supabase.co/auth/v1/callback` | Google returns to hosted Supabase Auth |
| Supabase Site URL | `http://127.0.0.1:5173/` | Default application return URL for this local-only setup |
| Supabase Redirect URLs entry | `http://127.0.0.1:5173/` | Exact return URL supplied by the frontend |

1. Select the intended Google Cloud project and its Web application OAuth client.
2. Add the origin and callback above without removing entries used by other applications.
3. Check **Google Auth Platform → Audience** and **Data Access**.
4. Use an external audience when accounts outside a Workspace organization need access.
5. Keep only `openid`, `userinfo.email`, and `userinfo.profile` scopes for this login.
6. Keep the existing testing status for this local validation.
7. If you manage a test-user list, add the intended test accounts there.
8. Open the Google provider under Supabase **Authentication → Sign In / Providers**.
9. Enter the selected Web client's Client ID and Client Secret directly in that provider form.
10. Enable the provider and save the form.
11. Keep nonce-check bypass and email-less accounts disabled, if those options are available.
12. Configure the Site URL and Redirect URLs under Supabase **Authentication → URL Configuration**.
13. For a project shared with another application, review its existing Site URL before replacing it.
14. Disable unused authentication providers and anonymous sign-in in the dedicated project.
15. Keep new user signup enabled so a friend's first OAuth login can create a Supabase identity.

Google documents an exception for basic identity scopes in testing mode.
Those scopes do not require membership in the test-user list or expire authorization after seven days.
The application approval list remains the access boundary, regardless of Google's testing settings.

The Google Client Secret belongs in Supabase's provider configuration only.
The backend and frontend do not need it. The callback on port `54321` applies to a local Supabase stack, not this setup.

**Checkpoint:** Both saved redirect configurations match. Google is enabled, with only the required identity scopes.

### 4. Switch the private local environment

1. Copy the project's public `sb_publishable_` key from Supabase API Keys.
2. Preserve all unrelated settings in the private root `.env`.
3. Remove `TNR_LOCAL_USER_ID` and `VITE_LOCAL_MODE`.
4. Set the following values together:

```dotenv
TNR_SUPABASE_URL=https://PROJECT_REF.supabase.co
TNR_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_WITH_PUBLIC_KEY
VITE_SUPABASE_URL=https://PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_WITH_PUBLIC_KEY
```

| Variable | Consumer | Classification |
| --- | --- | --- |
| `TNR_SUPABASE_URL` | FastAPI JWT verifier | Public project origin |
| `TNR_SUPABASE_PUBLISHABLE_KEY` | FastAPI Google invitation verification | Same public API key as the frontend |
| `VITE_SUPABASE_URL` | Browser Supabase SDK | Public project origin |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Browser Supabase SDK | Public API key, not an access token |

5. Preserve the existing Supabase application and operator connection settings.
6. Restart the existing backend and frontend using the [development commands](development.md).
7. Confirm that only one backend worker and one Vite server use those ports.
8. Check `http://127.0.0.1:5173/api/health` for `{"status":"ok"}`.
9. Open `http://127.0.0.1:5173/` and confirm that the Google login button appears.

Environment changes require both processes to reload their configuration.
If Vite returns dependency-cache errors, stop its server before restarting with `npm run dev -- --force`.
Do not clear browser storage during an OAuth exchange.

**Checkpoint:** Unauthenticated data requests return `401`, and the login page loads without application data.

### 5. Link the owner explicitly

1. Sign in through the application's Google button.
2. Confirm that the return URL uses `127.0.0.1:5173` and no longer contains the authorization code.
3. Expect **Accesso riservato** before approval.
4. Verify that `GET /api/me` returns `403` in the browser Network panel.
5. In Supabase **Authentication → Users**, verify the account, Google identity, and Supabase user UUID.
6. Create and verify a PostgreSQL backup before the identity-link operation.
7. From `backend/`, run the following command with the verified UUID:

```sh
.venv/bin/python -m app.access link-owner --subject OWNER_SUPABASE_USER_UUID
```

8. Confirm that the original profile ID, role, active status, subscriptions, and read states remain unchanged.
9. Select **Verifica di nuovo** in the application.

**Checkpoint:** `/api/me` returns `200` with the existing administrator profile. The original sources and preferences remain available.

### 6. Verify sessions and a reader

Use a separate browser profile for the reader. Keep each OAuth exchange in the browser profile that started it.
The reader test needs a second real Google account. Synthetic-token tests cannot replace this check.

| Test | Expected result |
| --- | --- |
| Reload after owner login | The same administrator session and preferences return |
| Session renewal | The SDK renews the session, and subsequent API requests succeed |
| Logout, then reload | Login screen, with no previous account's application data |
| Unapproved reader login | Approval screen and `403` from `/api/me` |
| Direct API request with that reader's valid token | `403` from `/api/articles` and `/api/sources` before approval |
| Explicit reader approval | `invite` creates an active reader with no copied subscriptions or read states |
| Reader selects sources | Only the reader's subscriptions change |
| Reader requests an administrative operation directly | `403`, with no catalog change |
| Reader logout and owner login | Owner preferences return without the reader's interface state |
| Reader revocation | Existing reader session receives `403` on its next protected request |

Use the [operator commands](authentication.md#approve-the-administrator-and-friends) for approval, revocation, and explicit restoration.
Run direct API probes locally with the current session token, without printing or saving it.
Record only status codes and necessary nonsecret results. Do not export HAR files or copy bearer headers into shared logs.
For renewal, observe an actual SDK token refresh and a subsequent successful API request.
Do not report renewal from a page reload alone.

**Checkpoint:** Record actual results privately, including untested renewal. Deployment is a separate operation.

### Recovery and completion record

For local-only recovery, stop both servers before changing authentication settings.
Remove the four Supabase settings listed above and restore the reserved local user and `VITE_LOCAL_MODE=true`.
Restart only on loopback. This does not delete identity links or personal data.
Do not use this bypass after public deployment.

Record the date, code revision, checks, manual settings, owner-link outcome, and remaining real-session tests.
Keep user UUIDs, keys, tokens, and private database paths out of the committed record.
Automated tests use mocked identity services and real Alembic migrations on disposable local PostgreSQL databases.
They do not establish that Google, Supabase, or a real browser session works.
