# Source proposals

This feature requires migration `0006` and explicit runtime grants before deployment.
No migration, deployment, AI integration, or account connection is performed by installing this code.

## Reader workflow

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

## Administrator workflow

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

## State, ownership, and transactions

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

## API

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

## Coordinated publication procedure

1. Review the local diff and tests. Authorize commit, push, migration, grants, and deployment separately when ready.
2. Record the remote revision and current grants with a read-only operator check. Confirm the existing target and backups.
3. Obtain and verify a recoverable database backup. Preserve existing identities, invitations, subscriptions, and reading states.
4. Coordinate collector inactivity and apply only the additive `0005 → 0006` migration with the operator connection.
5. Apply `backend/sql/enable_source_proposals.sql` and inspect `backend/sql/check_app_role.sql` results.
6. Confirm `tnr_app` has SELECT/INSERT/UPDATE on proposals and USAGE on its sequence, without DELETE or role-management privileges.
7. Confirm PUBLIC, anon, authenticated, and service_role have no access to the new table or sequence.
8. Deploy the backend manually on Render, using the reviewed revision. Verify health and authorized proposal endpoints.
   Use that revision for operator access commands as well; do not run an old `app.access` during rollout.
9. Publish the frontend on Vercel only after backend compatibility is confirmed.
10. Check reader isolation, approval, cancellation, both languages, counter refresh, and the installed-app return path.

A push to main can publish the frontend before a manual backend release.
Prefer two owner-authorized publication steps: commit and push the backend/schema changes first, with the old frontend unchanged.
Apply the migration and grants, deploy that backend revision manually, and verify it.
Then commit and push the frontend changes. This preserves the automatic main-only Vercel path without exposing an incompatible UI.
If the owner chooses a single combined commit, temporarily pausing Vercel deployment requires separate cloud-configuration authorization.
Do not enable the new frontend while its API is unavailable.
The previous manual Vercel recovery did not verify automatic deployment. The owner push of
`dab1c25` on 2026-11-09 triggered a Vercel deployment that reached Ready / Production.
Continue to verify the expected commit and status after each push.
Render deployment and migrations remain manual. Never initialize or reimport the populated remote database.

For rollback, revert application releases while keeping the additive table and grants for investigation.
Do not downgrade the production database: dropping `source_proposals` destroys proposal history.
The transfer utilities now require `0006` at both ends and include proposals and their sequence.
They remain operator-only tools, not part of this rollout. Do not run them against the existing populated Supabase database.

## Verification scope

Automated tests use real Alembic migrations on temporary SQLite files or isolated local PostgreSQL databases.
The PostgreSQL concurrency regression pauses approval after its final proposer read and
pauses revocation before commit. It checks both operation orders, observes a real advisory
lock waiter, and verifies the final decision and subscription. Both cases failed before the fix.
Feed downloads are mocked. No live publisher, AI provider, or Supabase database is used for tests.
Frontend behavioral tests cover submission, consent, cancellation, approval, rejection, linking, counter updates, and language changes.
Validation completed on 2026-11-09:

- SQLite suite after the access-lock fix: 442 passed, 33 PostgreSQL-only checks skipped.
- PostgreSQL 17 suite on a disposable loopback container: 474 passed, one SQLite backup check skipped.
- Frontend: 66 tests passed. ESLint, TypeScript, Prettier, and the production build passed.
- Ruff lint and format checks passed. Git whitespace checks and local documentation links passed.
- Browser: desktop and a 390 × 844 viewport, Italian/English, name-only submission, explicit approval through an existing source, persisted result, and cancellation.
- No browser console errors were observed in the checked reader flow. The build reports a nonblocking chunk-size warning above 500 kB.

The local personal SQLite database remains at revision `0004`; it was inspected read-only and was not migrated.
The authorized backend publication on 2026-11-09 started from remote revision `0005`.
A private schema backup was restored into a disposable local PostgreSQL database;
all restored table counts and content digests matched the consistent source snapshot.
With Render temporarily suspended, migration `0006` and its runtime grants were applied.
All prior table contents remained identical. The new table was empty, runtime privileges
matched the documented limits, and Data API roles had no schema, table, or sequence access.
Render resumed and successfully deployed backend commit `dab1c25` manually.
The production runtime credential could read the new table. Direct and Vercel-proxied
health requests returned `200`; anonymous proposal/profile requests returned `401`, with
`private, no-store` cache control. Check the new frontend after its separate publication push.
Live feed validation, physical mobile devices, and the installed-PWA lifecycle remain
unverified. Automated tests use mocked feeds and isolated identities.
English documentation follows the project's concise-writing guidance; no full ASD-STE100 dictionary audit or certification is claimed.
Temporary browser servers were stopped after local verification. Restore rehearsal databases
are deleted after comparison; private backups and release reports remain outside Git.
