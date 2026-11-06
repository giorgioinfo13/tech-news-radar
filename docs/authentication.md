# Backend authentication and access approval

The backend verifies Supabase access tokens and accepts only explicitly approved application users.
The frontend login, Google provider setup, browser sessions, and deployment remain separate steps.
This change does not configure cloud accounts or authorize a public deployment.

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

## Configuration

Set the project origin in the private root `.env` or backend environment:

```dotenv
TNR_SUPABASE_URL=https://PROJECT_REF.supabase.co
```

Remove `TNR_LOCAL_USER_ID` when you enable Supabase authentication.
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
This workflow becomes available to users after the frontend login step.
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

## Session and Google setup limits

JWT verification does not query `auth.sessions` on every request.
A Supabase logout or session revocation does not invalidate an already issued access token before its expiry.
For immediate application access removal, use the local access-revocation command against the application database.
The later frontend must clear local session data on logout and handle expired tokens through Supabase's session APIs.

Configure Google as the intended sign-in provider during the authorized cloud setup.
Disable unused sign-in methods and anonymous sign-in there.
The backend verifies Supabase user sessions. It does not infer the current OAuth provider from user-editable metadata.
Google origins, Supabase callbacks, application redirects, and CORS need validation with the actual frontend URLs.
Google test-user settings do not replace the application's approval list.
The official Google button and the Supabase frontend integration remain part of the frontend step.

## Verification

Tests use generated EC/RSA signatures, mocked JWKS HTTP responses, and real Alembic migrations on disposable databases.
They check malformed, expired, forged, wrong-project, wrong-audience, anonymous, and privileged-role tokens.
They also check key rotation, cache behavior, upstream failure, owner preservation, explicit approval, personal isolation, and revocation.
The tests do not use the personal Supabase project or live news services.

A complete Google login, Supabase signing-key compatibility, OAuth redirects, and deployed session behavior remain unverified until cloud setup.

Validation on 2026-11-06:

- SQLite: 289 tests passed. Two PostgreSQL-only checks were skipped.
- PostgreSQL 17.11 in an isolated local container: all 291 tests passed.
- Ruff lint, Ruff format, dependency checks, and local documentation links passed.
- No frontend files changed, so frontend checks were not run.
- No personal database, Supabase project, Google account, or cloud configuration was changed.

## Official references

- [Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts)
- [Supabase JWT claims](https://supabase.com/docs/guides/auth/jwt-fields)
- [Supabase signing keys](https://supabase.com/docs/guides/auth/signing-keys)
- [Supabase sessions](https://supabase.com/docs/guides/auth/sessions)
- [Google sign-in through Supabase](https://supabase.com/docs/guides/auth/social-sign-in/auth-google)
- [PyJWT verification and key caching](https://pyjwt.readthedocs.io/en/latest/api.html)
