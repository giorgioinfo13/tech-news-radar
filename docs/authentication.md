# Authentication and access approval

The backend verifies Supabase access tokens and accepts only explicitly approved application users.
The frontend provides Google sign-in, browser session recovery, logout, and personal source selection.
Google provider setup and deployment still require separate authorization. Installing the code does not configure cloud accounts.

Use the [local Google login procedure](local-google-login.md) to configure and verify the first real session with SQLite.

## Identity and permission boundary

The browser must send a Supabase **access token** in `Authorization: Bearer <access-token>`.
A Google ID token, Supabase API key, database password, or service-role token is not an application access token.
The backend does not accept tokens from URLs, cookies, or user-selection headers.

The verifier checks the signature, exact issuer, `authenticated` audience, expiry, issue time, session UUID, and subject UUID.
It accepts ES256 and RS256 signatures from the configured project's public JWKS endpoint.
It rejects anonymous users and tokens whose database role is not `authenticated`.
This token role is not the application's `admin` or `reader` role.
The application loads its role and active status from `app_users` on every request.
Neither `user_metadata`, `app_metadata`, email addresses, nor Google test-user lists grant application access.

Revision `0004` adds a nullable, unique `supabase_subject` to `app_users`.
Existing profiles and personal data keep their IDs. No profile receives an identity automatically.
The backend looks up the verified subject through this link. It never treats a JWT subject as an application profile ID.
No HTTP endpoint creates profiles, changes roles, or links the reserved administrator.
An unapproved Supabase user receives `403` and creates no application data.

The application database supports one Supabase Auth project.
Do not change `TNR_SUPABASE_URL` to another project while keeping existing identity links without a separate migration plan.
SQLite and PostgreSQL use the same authentication and permission code.
No foreign key to the remote `auth.users` table is required.

The optional `POST /api/internal/collect` is a machine-only exception with a separate bearer secret.
It can only scan existing due sources; it cannot read personal data, approve users, or change the catalog.
User access tokens do not authorize this endpoint, and its secret does not authorize user endpoints.
It returns `404` while unconfigured. See [external collection](development.md#collection-on-render-free) for activation and rotation.

## Configuration

Set these values in the private root `.env` for local integration testing, after cloud setup is authorized:

```dotenv
TNR_SUPABASE_URL=https://PROJECT_REF.supabase.co
VITE_SUPABASE_URL=https://PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_WITH_PUBLIC_KEY
```

Both URLs must identify the same project. Only the `VITE_*` values enter the browser build.
Use the project's public publishable key, never a secret key, service-role key, or database password.
The frontend accepts `sb_publishable_` keys; legacy JWT API keys are not supported by this configuration.
The backend needs only `TNR_SUPABASE_URL` to verify tokens. Restart Vite after environment changes; rebuild production assets after changes.

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

Apply migration `0004` explicitly to an authorized database before you enable the API or run access commands.
The API and access commands never apply migrations automatically.
Back up existing data before migration. Supabase migrations still require separate owner authorization.
Downgrading to `0003` removes identity links and blocks Supabase access, but preserves profiles, subscriptions, and read states.

## Approve the administrator and friends

This version uses operator approval by Supabase user UUID. It does not send invitation emails.
The person first authenticates with Google through Supabase, then waits for your approval before accessing application data.
Until approval, the frontend shows **Accesso riservato**. After approval, the person can select **Verifica di nuovo** without signing in again.
A Supabase account alone does not mean that the person is an approved application user.

Before provisioning, inspect the correct Supabase project's user record in its authenticated dashboard.
Confirm the person's identity, Google identity, and user UUID through a trusted channel.
Use the Supabase user UUID, not a Google subject, application profile UUID, email, or UUID supplied without verification.
Do not paste access tokens or private identity lists into Git, issue reports, or shared logs.

Run the following commands from `backend/` against the intended application database.
Replace the uppercase placeholders with verified UUIDs. These examples are not ready to run.
The commands use `TNR_MIGRATION_DATABASE_URL` when set, otherwise `TNR_DATABASE_URL`.
They need write access to `app_users`. The running API needs only read access to that table.
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

The [local verification record](local-google-login.md#owner-login-check-on-2026-11-06) covers the first real Google login and owner link.
Deployed session behavior remains unverified. Local checks do not establish production readiness.

Frontend-step validation on 2026-11-06:

- SQLite: 289 tests passed. Two PostgreSQL-only checks were skipped.
- PostgreSQL was not rerun for this frontend change. The preceding backend step passed all 291 tests on isolated PostgreSQL 17.11.
- Ruff lint and format checks passed.
- Frontend: 35 tests passed; ESLint, TypeScript, Prettier, and production build passed.
- Local Chrome screenshots checked the login and initial source-selection layout. Real Google sign-in remains unverified.
- No personal database, Supabase project, Google account, or cloud configuration was changed.

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
