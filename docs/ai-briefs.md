# Shared hourly AI digest

Status: local implementation. Gemini generation and automation remain disabled.
A code-level contract gate also blocks live activation, even if configuration flags are enabled.

The selected transport is OpenRouter BYOK, with the paid `google/gemini-3.1-flash-lite` model.
The direct Google transport remains an explicit alternative; neither route is active.
AI Pro credits can cover eligible consumption. They do not make the API a free model.
There is no automatic model or provider fallback. The former Xing runtime, tokenizer, and trial commands remain removed.
DeepSeek is a possible future experiment, not an enabled model or a fallback.

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
| Input per attempt | 3,500 tokens, subject to the unresolved schema-count contract |
| Combined visible output and thinking | 500 tokens |
| Reservation per attempt | 4,000 tokens; 1,625,000 nano-USD direct or 1,706,250 nano-USD BYOK |
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
BYOK adds a prudential 5% fee reserve: 81,250 units, for a total of 1,706,250 nano-USD.
Both transports use the same monthly ledger; changing transport cannot reset spent budget.
These remain conditional cost estimates until the input and provider contracts are verified.

A reservation equal to the remaining budget is accepted. The next reservation is rejected.
Concurrent requests cannot both claim the last amount or daily attempt.
Each job records its original budget month and reserved amount.
A new month selects a new ledger row. Late completions never refund or update either month's money total.
The daily reset preserves leases and cooldowns. The monthly ledger survives restart and seven-day job cleanup.
A downgrade refuses to discard any nonzero monthly reservation.

`monthly_budget` is distinct from `daily_limit`, `temporary_limit`, `invalid_output`, and `model_unavailable`.
`activation_required` explains the code-level activation gate. `input_limit` reports an oversized counted input.
The frontend translates these states into Italian and English. The operator POST route enforces the same budget and returns HTTP 429 when exhausted.
Saved results remain readable. `safety_stop` persists after inconsistent usage or model identity, including across month resets.
Diagnostics contain only allowlisted labels and bounded integers, never raw provider content or headers.

This ledger limits requests through this application only. It does not read Cloud promotional balances.
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
This unresolved input bound keeps `LIVE_CONTRACT_VERIFIED = False` in `app.ai_gemini`.
There is no environment override for this gate. Simulated responses cannot satisfy it.
The [Google staff clarification](https://discuss.ai.google.dev/t/gemini-api-counttokens/188451) says that schemas inside generationConfig are excluded from countTokens.
The [GenerateContent thinking guide](https://aistudio.google.com/docs/thinking?generate-content=true#token-limits) describes a hard combined output/thinking cutoff.
This is the GenerateContent variant, not evidence transferred from the separate Interactions API.
MINIMAL does not mean zero reasoning. Response checks enforce input ≤3,500, combined output ≤500, exact accounting, and the authorized model.
Reported usage on HTTP errors must also stay within the actual preflight count, not just the global 3,500-token limit.
An accounting anomaly persists `safety_stop`; later calls remain blocked across restarts and period changes.
These checks cannot retroactively prevent provider consumption.

### Activation evidence

| Requirement | Evidence and remaining work |
| --- | --- |
| Fixed model and structured JSON | The [model page](https://aistudio.google.com/docs/models/gemini-3.1-flash-lite) lists structured output and thinking support. The [REST example](https://aistudio.google.com/docs/structured-output?generate-content=true) uses `responseFormat.text.schema`. Account availability remains untested. |
| Direct output ceiling | The GenerateContent guide documents a combined cutoff. The payload sets 500, and simulated tests reject 501 or inconsistent totals. No live output has been checked. |
| Standard text tariff | The pricing table lists USD 0.25/million input and USD 1.50/million output including thinking. The reservation remains conditional on the complete billable input bound. |
| Complete direct input bound | Unresolved: `countTokens` excludes the output schema. No documented upper bound for its billable overhead was established. |
| Complete BYOK input bound | Unresolved: the router translates the request. Native Google counting does not establish a bound for that translation. `count_input` remains blocked. |

To resolve the input blocker, obtain a provider-documented calculation that bounds every billable input component for the exact request.
The required result is `billable_input <= preflight_bound <= 3500`, including the schema and any provider-added formatting.
For BYOK, the result must apply to the translated Google AI Studio request, with the selected routing and no fallback.
Keep the combined output limit at 500 and the existing money reservation unchanged.
Do not substitute characters/4, a byte count, an arbitrary allowance, or separately counted schema text for that guarantee.
Copying the schema into the prompt does not remove the original schema's possible overhead.
Do not remove structured output or silently switch providers to bypass this requirement.
An isolated live test can check observed behavior after these prerequisites are met. It cannot prove a universal billing bound.
Until then, both code gates remain false, even with keys and configuration flags present.

## OpenRouter BYOK preparation

`TNR_AI_TRANSPORT=openrouter_byok` selects the prepared adapter. `gemini` explicitly selects the direct adapter.
The model is fixed in code; API callers cannot select DeepSeek or another provider.
The BYOK payload allows only Google AI Studio, requests strict JSON and minimal reasoning, and disables provider fallbacks.
No tools, plugins, conversation history, automatic retries, or explicit cache are included.
Usage validation requires `is_byok: true`, the expected model/provider, bounded native token counts, and exact decimal costs.
OpenRouter completion tokens include reasoning; the validator does not count them twice.
Positive paid-provider costs are accepted within the reservation. Missing or inconsistent cost data stops further work.
See [usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting) and
[reasoning accounting](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

**This is a local preparation, not an activatable integration.** `OpenRouterBYOK.count_input` fails closed:
no documented counter was found that bounds the router's complete translated Gemini input, including the schema.
Tests substitute a simulated counter. They cannot validate that missing provider contract.
A separate code gate remains false. Changing that gate alone does not implement counting.
The [public model catalog](https://openrouter.ai/google/gemini-3.1-flash-lite) lists Google AI Studio,
but model availability does not prove BYOK eligibility for this account or the absence of internal provider retries.

Before activation, verify Google AI Studio BYOK support and the required OpenRouter plan without switching silently to Vertex.
The provider key would be stored in OpenRouter integrations; only the OpenRouter API key belongs in backend `TNR_OPENROUTER_API_KEY`.
This phase connects neither. The direct route would instead use backend `TNR_GEMINI_API_KEY`.
Set the provider's Shared capacity fallback to **Never use shared capacity for any model on this provider**.
`allow_fallbacks: false` alone does not enforce BYOK-only. Confirm a single applicable prioritized key and model restriction.
See [BYOK routing](https://openrouter.ai/docs/guides/overview/auth/byok).
No management credential, account configuration, key upload, or cloud change is implemented by the app.

Activation also requires verification of prices, fee accounting, translated parameters, total billable input/output,
BYOK-only enforcement, upstream retry behavior, and privacy conditions for the additional OpenRouter processor.
A future DeepSeek experiment requires an explicit model, tariff, token contract, privacy review, and simulated tests.
Google credits do not pay an OpenRouter or DeepSeek invoice.

## Monthly capacity and cost

Standard Gemini text rates, checked 2026-11-09: input USD 0.25/million; output including thinking USD 1.50/million.
Source: [Google pricing](https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite).
At the maximum 3,500 input + 500 output per hourly attempt:

| Calendar days | Attempts | Input tokens | Output incl. thinking | Direct USD | BYOK reserve incl. 5% USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| 28 | 672 | 2,352,000 | 336,000 | 1.092 | 1.1466 |
| 30 | 720 | 2,520,000 | 360,000 | 1.170 | 1.2285 |
| 31 | 744 | 2,604,000 | 372,000 | 1.209 | 1.26945 |

These are calculated ceilings under the stated contract, not observed usage or a guaranteed invoice.
Input includes instructions and schema, not only RSS text. Reads are free of inference; skipped/unchanged editions reduce usage.
Failures keep the local reservation. No cache or promotional discount reduces the reserved amount.

The [AI Pro developer benefit](https://developers.google.com/profile/help/benefits?hl=en) provides USD 10/month of eligible Google credits.
Both estimates fit within USD 10 and the app's USD 2 cap if tariffs and token bounds hold.
Credits must be applied to the correct billing account and remain available; other eligible services can consume them.
The API remains paid. A Google credit cannot cover an OpenRouter fee or DeepSeek billing.

Current [OpenRouter pricing](https://openrouter.ai/pricing) lists a fee-free BYOK allowance of USD 25,000/month
in list-price inference on pay-as-you-go plans, then a 5% fee.
The Free plan does not list BYOK support. Account eligibility and available allowance were not checked.
The app reserves 5% regardless; OpenRouter charges, if any, are separate from Google and may require OpenRouter funds.

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

1. Keep all generation and workflow flags false. Resolve the [contract blockers](#token-and-provider-contract) first.
2. In a separately authorized release, record the target and make a verified backup.
3. Inspect the actual remote Alembic head. The local chain is `0006 → 0007 → 0008 → 0009`.
4. Apply only missing migrations. Existing revisions are unchanged in this Gemini phase.
5. Review `backend/sql/enable_ai_briefs.sql` with the owner connection after `0009`.
6. Grant SELECT/UPDATE on control, CRUD on jobs, and SELECT/INSERT/UPDATE on budget to `tnr_app`.
7. Verify no DELETE/TRUNCATE on budget and no Data API access. Do not change user roles or invitations.
8. Release the backend with AI disabled. Verify the reader and saved-cache routes before any frontend release.
9. Verify the selected transport and its BYOK prerequisites, then configure its backend key privately after explicit authorization.
10. Keep the key out of `VITE_*`, Git, logs, chat, screenshots, and API responses. Do not reuse the trigger credential.
11. Authorize a fresh isolated live test separately. Never reuse a closed OpenRouter trial directory or marker.
12. Enable scheduling only after contract, privacy, model, billing, and real-output checks pass.

Tests require no key. Do not connect a key merely to run the suite.
Transfer tools now require a `0009` snapshot and preserve monthly reservations.
A database restore must not roll back the current ledger and reopen spent budget. Keep generation off until reconciliation.
Cloud migration, runtime grants, connectivity, billing balance, and live inference checks remain unexecuted.
