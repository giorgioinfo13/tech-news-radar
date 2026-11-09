# Shared hourly AI digest

Status: local implementation. Gemini generation and automation remain disabled.
Generation requires explicit deployment configuration, privacy review, and acceptance of the prudential budget risk.

The only transport is the direct Google Gemini Developer API, with the paid `gemini-3.1-flash-lite` model.
Generation remains inactive. The OpenRouter BYOK adapter and its configuration are removed.
AI Pro credits can cover eligible consumption. They do not make the API a free model.
There is no automatic model or provider fallback. The former Xing runtime, tokenizer, and trial commands remain removed.
Other models or providers require a separate integration review.

## User behavior

Approved readers share one saved digest across the catalog, independent of followed sources or reading states.
The target is one edition per UTC hour, covering the previous 24 hours.
Opening, navigating, refreshing, or returning to the app only reads saved data.
The page has no generation button. Italian is the default interface, with English translations.
Generated summaries remain Italian in either interface language.

The backend selects and deduplicates at most 12 articles from enabled public sources.
Selection balances categories and limits each domain to three articles.
At least two useful descriptions are required. Insufficient material causes no provider call.
The digest targets 120–180 words. Local validation accepts 100–200 words.
Only selected article IDs can become citations. The backend supplies the source links.
The page shows generation time, the news interval, and the RSS-only input notice.
The model never receives complete articles, user identities, email, tokens, subscriptions, or reading history.
Public RSS text can contain personal data about people in the news.

Saved editions and jobs expire after seven days, on the next read or scheduled invocation.
Article retention is unchanged. Monthly money totals remain stored independently of job cleanup.
The reader and saved digests remain available when AI is disabled, unavailable, or out of budget.

## API, authorization, and durable admission

`GET /api/briefs/digest` uses existing approved Google/Supabase authorization and respects revocation.
It performs no token-count or generation request. It always returns `can_generate: false`.
The former category GET and generation POST routes are removed and return HTTP 404.
Only the shared digest reader and the operator invocation remain exposed.

`POST /api/briefs/internal/run` uses a separate operator bearer credential with constant-time comparison.
It accepts no model, period, category, price, or budget overrides.
The response contains only a recognized status and remaining daily attempts.
The operator credential cannot read digests or impersonate an app user.
Existing roles, invitations, approvals, revocations, and personal data remain unchanged.

Admission locks the existing access-decision gate and singleton control row.
PostgreSQL supplies its wall clock after the lock acquisition.
The same short transaction checks quota, money, cooldown, deduplication, and lease ownership.
It reserves money and 4,000 tokens, then inserts the unique hourly job.
No HTTP call holds a database transaction. A second persistent dispatch check runs after token counting.
That check rejects revoked access, expired leases, changed UTC hours, and a previously dispatched job.

| Control | Limit |
| --- | --- |
| Project attempts per UTC day | 24 |
| Reserved tokens per UTC day | 96,000 |
| Counted input per attempt | 3,500 tokens; complete billable coverage is not guaranteed |
| Combined visible output and thinking | 500 tokens |
| Reservation per attempt | 4,000 tokens; 1,625,000 nano-USD |
| Concurrent generation | One |
| Attempts per UTC hour | One |
| Global cooldown | At least 60 seconds |
| Retry of a failed or uncertain edition | None |
| Local calendar-month budget | USD 2.00, UTC |

Configuration can reduce daily limits, never increase these ceilings.
Failures preserve the full lease and all reservations. Success also retains the full money reservation.
Expired work becomes interrupted. Restart, Render suspension, and lease expiry never resubmit uncertain work.
The service rejects repeated material across retained jobs, including failed jobs.
A new hour does not authorize another attempt with the same material.

## Local monetary budget

`ai_brief_budget` stores one row per calendar month UTC.
`reserved_nano_usd` uses an integer `BIGINT`. One USD equals 1,000,000,000 units.
The cap is 2,000,000,000 units. No floating-point money calculation or currency conversion is used.
The fixed reservation is `3500 * 250 + 500 * 1500 = 1,625,000` units, or USD 0.001625.
No intermediary fee is added to new reservations.
Existing monthly totals remain unchanged, including any reservations created by earlier application versions.
Removing a provider does not refund or reset those totals. No database migration is needed for this simplification.
This is a prudential reservation, not a guaranteed maximum provider charge.
The owner accepted this limitation on 2026-11-09. The implementation does not claim complete billable-input coverage.

A reservation equal to the remaining budget is accepted. The next reservation is rejected.
Concurrent requests cannot both claim the last amount or daily attempt.
Each job records its original budget month and reserved amount.
A new month selects a new ledger row. Late completions never refund or update either month's money total.
The daily reset preserves leases and cooldowns. The monthly ledger survives restart and seven-day job cleanup.
A downgrade refuses to discard any nonzero monthly reservation.

`monthly_budget` is distinct from `daily_limit`, `temporary_limit`, `invalid_output`, and `model_unavailable`.
`activation_required` means the deployment has not enabled acceptance of the prudential budget risk. `input_limit` reports an oversized counted input.
The frontend translates these states into Italian and English. The operator POST route enforces the same budget and returns HTTP 429 when exhausted.
Saved results remain readable. `safety_stop` persists after inconsistent usage or model identity, including across month resets.
Diagnostics contain only allowlisted labels and bounded integers, never raw provider content or headers.

This ledger strictly limits reserved amounts through this application, not the Google invoice.
Provider overhead, accounting discrepancies, or a tariff change can make actual charges exceed reservations.
A detected discrepancy stops later requests, but cannot undo the charge for the current attempt.
The application does not read Cloud promotional balances.
It cannot control other applications, keys, projects, or Google services.
The local USD 2.00 cap is distinct from the owner's reported Google EUR 2.00 project cap.
No exchange-rate equivalence is assumed. Google caps and billing reports can lag.

## Token and provider contract

The direct Google adapter uses plain REST `countTokens` and `generateContent` on a fixed HTTPS origin.
It disables redirects and environment proxies. HTTP transport has no automatic retries.
The request has one candidate, `maxOutputTokens: 500`, and `thinkingLevel: MINIMAL`.
The current REST schema uses `generationConfig.responseFormat.text` with `APPLICATION_JSON` and a JSON schema.
No tools, grounding, URL context, files, explicit remote cache, batch, continuation, or conversation history are sent.
No Xing tokenizer or template is used on the Gemini path.

The count request contains the same system instructions, RSS content, and generation configuration as generation.
Passing the schema to the count request does not prove that the provider counts its billable representation.
Complete billable-input coverage remains unverified. The accepted operating policy uses the count as a prudential admission check.
`TNR_AI_BUDGET_RISK_ACCEPTED=false` blocks counting and generation until the deployment explicitly selects this policy.
The former `LIVE_CONTRACT_VERIFIED` constant is removed. No setting or simulated response proves the missing guarantee.
The [Google staff clarification for a 3.6 Flash question](https://discuss.ai.google.dev/t/gemini-api-counttokens/188451) excludes schemas inside generationConfig from countTokens.
A [separate 3.5 Flash-Lite answer](https://discuss.ai.google.dev/t/gemini-3-5-flash-lite-counttokens-pricing-quota-schema-coverage-and-thinking-cap/189068) includes schema tokens.
Neither establishes a complete billable-input upper bound for this app's exact 3.1 Flash-Lite request.
The [GenerateContent thinking guide](https://aistudio.google.com/docs/thinking?generate-content=true#token-limits) describes a hard combined output/thinking cutoff.
This is the GenerateContent variant, not evidence transferred from the separate Interactions API.
MINIMAL does not mean zero reasoning. Response checks enforce input ≤3,500, combined output ≤500, exact accounting, and the authorized model.
Reported usage on HTTP errors must also stay within the actual preflight count, not just the global 3,500-token limit.
An accounting anomaly persists `safety_stop`; later calls remain blocked across restarts and period changes.
These checks cannot retroactively prevent provider consumption.

### Evidence and accepted limitations

| Requirement | Evidence and remaining work |
| --- | --- |
| Fixed model and structured JSON | The [model page](https://aistudio.google.com/docs/models/gemini-3.1-flash-lite) lists structured output and thinking support. The [REST example](https://aistudio.google.com/docs/structured-output?generate-content=true) uses `responseFormat.text.schema`. Account availability remains untested. |
| Direct output ceiling | The GenerateContent guide documents a combined cutoff. The payload sets 500, and simulated tests reject 501 or inconsistent totals. No live output has been checked. |
| Standard text tariff | The pricing table lists USD 0.25/million input and USD 1.50/million output including thinking. The reservation uses these rates as an estimate, without a complete billable-input guarantee. |
| Complete direct input bound | Unresolved: schema coverage has conflicting statements for other models. No complete billable-input upper bound was established for 3.1 Flash-Lite. |

The [REST countTokens reference](https://aistudio.google.com/api-reference/tokens/count-tokens) accepts the full `generateContentRequest`, including `generationConfig`.
It defines `totalTokens` as the tokenized prompt size. It does not document a complete billable-input upper bound for this request.
The [model-specific forum question](https://discuss.ai.google.dev/t/documented-billable-token-bounds-for-gemini-3-1-flash-lite-structured-text/198793) remained unanswered at the 2026-11-09 review.
A public question is not provider confirmation. No clarification request was sent from this project.

The owner accepted proceeding without a guaranteed complete billable-input upper bound.
This changes the activation prerequisite, not the available provider evidence.
The adapter still requires `countTokens.totalTokens <= 3500` before generation.
It still rejects observed input above the count, output plus thoughts above 500, and inconsistent accounting.
Any such anomaly persists `safety_stop`, with no automatic reset or refund.
No arbitrary schema allowance, characters/4 estimate, higher token limit, or relaxed output validation is introduced.
A future provider-documented upper bound can strengthen this policy. It is no longer required before a separately authorized trial.
A single successful trial establishes observed behavior only, not a universal billing guarantee.

## Direct Google configuration

`TNR_AI_TRANSPORT=gemini` is the only accepted value and the default.
An old `openrouter_byok` selection is rejected at startup instead of silently changing the destination.
Remove obsolete OpenRouter settings during a separately authorized deployment. Do not reuse an OpenRouter key for Google.
For a separately authorized trial, set `TNR_AI_BUDGET_RISK_ACCEPTED=true` in the backend environment.
This records the accepted prudential policy for that deployment. It does not enable generation by itself.
Both generation flags, privacy review, and a backend key remain independently required.
All flags, including budget acceptance, default to false. Older configuration cannot silently opt in.
Configure `TNR_GEMINI_API_KEY` privately only during the authorized activation.
Keep it separate from `TNR_AI_DIGEST_TRIGGER_SECRET`. Never use `VITE_*`, Git, logs, or chat for either secret.
The endpoint and model are fixed in code. No provider selection, fallback or intermediate billing service is available.
The previous BYOK preparation is retained in Git history and local investigation notes.

## Monthly capacity and cost

Standard Gemini text rates, checked 2026-11-09: input USD 0.25/million; output including thinking USD 1.50/million.
Source: [Google pricing](https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite).
At the reservation assumption of 3,500 input + 500 output per hourly attempt:

| Calendar days | Attempts | Input tokens | Output incl. thinking | Reserved USD |
| --- | ---: | ---: | ---: | ---: |
| 28 | 672 | 2,352,000 | 336,000 | 1.092 |
| 30 | 720 | 2,520,000 | 360,000 | 1.170 |
| 31 | 744 | 2,604,000 | 372,000 | 1.209 |

These are planned reservation totals, not observed usage or a guaranteed invoice.
The count request contains instructions and schema, but complete billable-input coverage remains unverified. Reads are free of inference; skipped/unchanged editions reduce usage.
Failures keep the local reservation. No cache or promotional discount reduces the reserved amount.

The [AI Pro developer benefit](https://developers.google.com/profile/help/benefits?hl=en) provides USD 10/month of eligible Google credits.
The estimated reservations fit within USD 10 and the app's USD 2 ledger limit. Actual charges can differ.
Credits must be applied to the correct billing account and remain available; other eligible services can consume them.
The API remains paid. Promotional credits are not an application-enforced spending cap.

## Privacy and billing conditions

The [paid service terms](https://aistudio.google.com/docs/terms#paid-services) exclude product improvement using paid-service prompts and responses.
The [abuse policy](https://aistudio.google.com/docs/usage-policies) describes 55-day retention and authorized review of flagged content.
It permits use for policy-enforcement models. This is not ZDR or a promise of no training of any kind.
The terms allow processing outside the EU. Italian and English public privacy notices describe the inactive integration and future transfers.

The owner reports an AI Pro monthly credit, a completed initial Gemini payment, Tier 1, and a EUR 2.00 project cap.
These account facts were not independently rechecked during this phase.
A positive prepaid balance after payment and actual model availability remain unverified.
The initial EUR 5 payment is not a universal Cloud spending ceiling.
[Gemini Prepay](https://aistudio.google.com/docs/billing) can incur overages during processing delays.
A negative balance is deducted from the next credit purchase. Other Cloud services can bill separately.
Auto-reload is reported off. “Always use this billing account” applies recurring promotional credits, not auto-reload.
Promotional credits can expire or serve other eligible usage. Do not assume the separate Cloud Free Trial covers Gemini Developer API.
The local month uses UTC, not the Google cap reset shown as PST or the AI Pro benefit's recurrence.

## Hourly scheduling on existing infrastructure

The prepared GitHub workflow targets minute 37 of each UTC hour and requires an explicit disabled-by-default repository variable.
The trigger client wakes Render with bounded health checks, then sends at most one generation POST.
It never retries an uncertain POST. Delayed runs use the current hour, without a backlog.
PostgreSQL controls admission independently of the workflow timer or in-memory state.
Schedules can be delayed or skipped. Render can suspend or restart. Hourly publication is a target, not a guarantee.
No new queue service, paid cron, or additional infrastructure is introduced.

## Coordinated publication plan — not executed

1. Keep generation and workflow flags false. Review the [accepted budget limitations](#token-and-provider-contract).
2. In a separately authorized release, record the target and make a verified backup.
3. Inspect the actual remote Alembic head. The local chain is `0006 → 0007 → 0008 → 0009`.
4. Apply only missing migrations. Existing revisions are unchanged in this Gemini phase.
5. Review `backend/sql/enable_ai_briefs.sql` with the owner connection after `0009`.
6. Grant SELECT/UPDATE on control, CRUD on jobs, and SELECT/INSERT/UPDATE on budget to `tnr_app`.
7. Verify no DELETE/TRUNCATE on budget and no Data API access. Do not change user roles or invitations.
8. Release the backend with AI disabled. Verify the reader and saved-cache routes before any frontend release.
9. Verify direct Google model availability and billing prerequisites, then configure its backend key privately after explicit authorization.
10. Keep the key out of `VITE_*`, Git, logs, chat, screenshots, and API responses. Do not reuse the trigger credential.
11. Authorize a fresh isolated live test separately. Never reuse a closed OpenRouter trial directory or marker.
12. Enable scheduling only after budget-risk acceptance, privacy, model, billing, and real-output checks pass.

Tests require no key. Do not connect a key merely to run the suite.
Transfer tools now require a `0009` snapshot and preserve monthly reservations.
A database restore must not roll back the current ledger and reopen spent budget. Keep generation off until reconciliation.
Cloud migration, runtime grants, connectivity, billing balance, and live inference checks remain unexecuted.

### First authorized live attempt

This procedure is not an activation authorization. Complete the deployment and account checks above before using it.

1. Record the accepted budget limitations and configure `TNR_AI_BUDGET_RISK_ACCEPTED=true` for this deployment.
2. Verify the paid project's available balance, exact model access, privacy acceptance, and deployed database privileges.
3. Keep the GitHub digest workflow disabled. Keep generation disabled until the supervised test window.
4. Set the backend daily limits to one attempt and 4,000 reserved tokens for the test.
5. Configure the backend secrets privately, then enable generation only for the authorized window.
6. Invoke the existing operator route once. Use its persistent reservation and dispatch checks.
7. Disable generation after the attempt, including after a timeout. Do not repeat an uncertain request.
8. Inspect the saved job status, safe diagnostics, and retained monetary reservation through an authorized operator connection.
9. For a successful result, verify the Italian summary, RSS notice, news interval, and selected source links.
10. Reload the saved digest as an approved reader. Confirm that reads create no new job or reservation.

One attempt can make one count request and at most one generation request.
The daily limit resets at midnight UTC. It is not a permanent one-shot switch.
An HTTP 200 response alone does not prove success: inspect the returned status and saved job.
A successful job means local output and usage checks passed. It does not prove future provider billing bounds.
Keep hourly scheduling disabled until the separate live-test review passes.
Retain reservations after failure and success. Do not clear a persistent safety stop to repeat the test.
