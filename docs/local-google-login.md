# Local Google login with SQLite

This procedure connects the existing local application to hosted Supabase Auth.
Application data stays in SQLite. Google and Supabase hold authentication data.
It does not deploy the application or transfer its news database.

Complete each checkpoint before the next section. Cloud changes require the owner's authorization.
See [authentication](authentication.md) for identity checks and operator-command behavior.

## 1. Check the local state

1. Check the branch, working tree, and listeners on ports `8000` and `5173`.
2. Confirm that each listener belongs to this repository before you stop or restart it.
3. Check the configured database type without printing credentials.
4. Confirm that the SQLite database uses Alembic revision `0005`.
5. Record the owner's profile ID, role, active status, identity-link status, subscriptions, and read-state counts privately.

The reserved owner ID is `00000000-0000-0000-0000-000000000001`.
An existing identity link must match the intended Supabase account. Do not replace a conflicting link.
The access commands use `TNR_MIGRATION_DATABASE_URL` when present, otherwise `TNR_DATABASE_URL`.
Both the API and operator commands must target the existing local database for this procedure.

**Checkpoint:** The database and owner are identified. No migration or replacement database is necessary.

## 2. Identify the Supabase project and current key

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

## 3. Configure Google and Supabase manually

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

## 4. Switch the private local environment

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

5. Preserve the existing SQLite connection and operator connection settings.
6. Restart the existing backend and frontend using the [development commands](development.md).
7. Confirm that only one backend worker and one Vite server use those ports.
8. Check `http://127.0.0.1:5173/api/health` for `{"status":"ok"}`.
9. Open `http://127.0.0.1:5173/` and confirm that the Google login button appears.

Environment changes require both processes to reload their configuration.
If Vite returns dependency-cache errors, stop its server before restarting with `npm run dev -- --force`.
Do not clear browser storage during an OAuth exchange.

**Checkpoint:** Unauthenticated data requests return `401`, and the login page loads without application data.

## 5. Link the owner explicitly

1. Sign in through the application's Google button.
2. Confirm that the return URL uses `127.0.0.1:5173` and no longer contains the authorization code.
3. Expect **Accesso riservato** before approval.
4. Verify that `GET /api/me` returns `403` in the browser Network panel.
5. In Supabase **Authentication → Users**, verify the account, Google identity, and Supabase user UUID.
6. Create a consistent SQLite backup with SQLite's backup API before the identity-link operation.
7. Verify the backup with `PRAGMA integrity_check`.
8. From `backend/`, run the following command with the verified UUID:

```sh
.venv/bin/python -m app.access link-owner --subject OWNER_SUPABASE_USER_UUID
```

9. Confirm that the original profile ID, role, active status, subscriptions, and read states remain unchanged.
10. Select **Verifica di nuovo** in the application.

**Checkpoint:** `/api/me` returns `200` with the existing administrator profile. The original sources and preferences remain available.

## 6. Verify sessions and a reader

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

**Checkpoint:** Record each actual result, including missing accounts or untested renewal. Stop before PWA or deployment work.

## Recovery and completion record

For local-only recovery, stop both servers before changing authentication settings.
Remove all three Supabase settings and restore the reserved local user and `VITE_LOCAL_MODE=true`.
Restart only on loopback. This does not delete identity links or personal data.
Do not use this bypass after public deployment.

Record the date, code revision, checks, manual settings, owner-link outcome, and remaining real-session tests.
Keep user UUIDs, keys, tokens, and private database paths out of the committed record.
Automated tests use mocked identity services and real Alembic migrations on temporary databases.
They do not establish that Google, Supabase, or a real browser session works.

### Preparation check on 2026-11-06

- Code revision: `396e952` on `main`.
- Backend: 74 tests passed across `test_auth.py`, `test_multiuser.py`, `test_migrations.py`, and `test_app.py`.
- Frontend: 35 tests passed across `auth.test.tsx` and `App.test.tsx`.
- The existing development proxy returned `{"status":"ok"}` from `/api/health`.
- Read-only inspection confirmed SQLite revision `0004` and an active, unlinked reserved administrator.
- The selected project's public JWKS endpoint returned an ES256 key.
- The owner reported `ECC (P-256)` for the current key in the Supabase dashboard.
- At this checkpoint, real Google login, session renewal, owner linking, and reader approval remained unverified.

This preparation changed documentation only. It did not change private configuration, database contents, or cloud settings.
Lint, format, type checks, and production builds were not rerun because application code did not change.

### Local configuration check on 2026-11-06

- Owner-supplied screenshots matched the Google origin, hosted Supabase callback, Site URL, and application redirect.
- The private root `.env` now selects Supabase authentication for both frontend and backend.
- The two local identity settings were removed. Unrelated configuration and the existing SQLite connection were preserved.
- Both development servers restarted on loopback, with one backend application worker and one Vite server.
- `/api/health` returned `200` through both FastAPI and the Vite proxy.
- `/api/me`, `/api/articles`, and `/api/sources` returned `401` without a token through both addresses.
- The public Supabase Auth settings endpoint accepted the publishable key and reported Google enabled and signup permitted.
- Email sign-in was also enabled. Disabling unused providers remains a manual configuration task.
- Chrome displayed the Google login button at the expected local origin.

No application code, identity links, or database schema changed in this configuration check.
At this checkpoint, real login, session renewal, owner linking, and reader approval remained pending.

### Owner login check on 2026-11-06

- The owner completed real Google login and returned to the expected local origin.
- The application showed **Accesso riservato**, and the backend recorded `403` from `/api/me` before approval.
- Read-only inspection of Supabase's authenticated dashboard verified the matching account, Google provider, and user UUID.
- SQLite's backup API created a local backup before the link operation. Integrity and foreign-key checks passed.
- The `link-owner` command linked that verified identity to the existing reserved administrator.
- A comparison against the backup confirmed that all other profile fields and all existing application rows remained unchanged.
- Preserved data included 11 sources, 3,429 articles, eight categories, 22 collection runs, 11 subscriptions, and zero read-state rows.
- Chrome displayed the administrator workspace and existing articles after approval.
- Reloading the page restored the same session and administrator workspace.
- Backend logs confirmed `200` from `/api/me`, `/api/sources`, and `/api/articles` after approval and reload.
- The owner reported that logout and a subsequent Google login worked. This result was not independently observed by the agent.

The profile still displays its original name, `Local owner`. Google login does not automatically rename existing application profiles.
The local backup is excluded from Git. No remote application database, schema, or cloud setting changed during this link operation.
At this checkpoint, token renewal and the second-account checks remained pending. The following record covers their subsequent verification.

Google's consent screen displayed the project's `PROJECT_REF.supabase.co` hostname.
This is expected with the default hosted Supabase Auth domain.
Brand verification and a custom authentication domain are separate configuration options described in the official Google-provider guide below.

### Reader and session checks on 2026-11-06

These checks used code revision `4939b2a`, the existing SQLite database, and a second real Google account in a separate Chrome profile.
A new local SQLite backup passed integrity and foreign-key checks before reader provisioning.
The application database contained 3,433 articles at that checkpoint. Normal collection continued during these checks.

The first Google attempt returned `400: invalid_request` without a specific cause.
The generated authorization redirect contained the expected Web client, callback, `code` response type, and `email profile` scopes.
A fresh login from the application succeeded without code or cloud-configuration changes. The initial error's cause remains unknown.

| Check | Observed result |
| --- | --- |
| Unapproved account | The UI showed **Accesso riservato** |
| Direct authenticated requests before approval | `/api/me`, `/api/articles`, `/api/sources`, and `/api/subscriptions` each returned `403` |
| Identity verification | The authenticated Supabase dashboard showed the matching Google account and user UUID |
| Explicit local approval | `invite` created an active reader with zero subscriptions and zero read-state rows |
| Initial source selection | The reader selected only Hacker News through the UI and saw its articles |
| Personal reading state | The reader marked one article read through the UI |
| Owner preservation | Profile fields, 11 subscriptions, and read-state rows matched the backup after the reader's changes |
| Explicit SDK refresh | `refreshSession()` produced a different access token, a later expiry, the same identity, and `TOKEN_REFRESHED` |
| Application requests after refresh | The normal API client returned the reader role, one subscription, and the personal reading state |
| Direct administrative request | A source `PATCH` with its unchanged name returned `403` |
| Revocation with a valid token | All four protected endpoints returned `403` while the Supabase session and unexpired token remained present |
| UI after revocation | The normal API client's next article request returned `403`, and the UI showed **Accesso riservato** |
| Data after revocation | The reader's subscription and read-state row remained intact. The owner's personal data remained unchanged |
| Explicit reactivation | At the owner's request, `activate` restored reader access. **Verifica di nuovo** reopened the workspace without another Google login |
| Preferences after reactivation | The UI retained Hacker News and the article marked read |

The session check explicitly invoked the SDK refresh method. It did not wait for the automatic timer or natural token expiry.
Diagnostic code kept tokens inside the browser and sent them only to the configured authentication service or same-origin API.
Recorded diagnostic results contain status codes, counts, and boolean checks, without token values.
No application code, schema, or cloud configuration changed during these tests.
The second account remains an active reader. The original account remains the administrator.
Documentation checks passed. Automated tests, lint, and builds were not repeated because application code did not change.

## Official references

Configuration references checked on 2026-11-06:

- [Supabase Google provider](https://supabase.com/docs/guides/auth/social-sign-in/auth-google)
- [Supabase redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
- [Supabase signing keys](https://supabase.com/docs/guides/auth/signing-keys)
- [Supabase PKCE flow](https://supabase.com/docs/guides/auth/sessions/pkce-flow)
- [Supabase session refresh](https://supabase.com/docs/reference/javascript/auth-refreshsession)
- [Google audience and testing exceptions](https://support.google.com/cloud/answer/15549945)
