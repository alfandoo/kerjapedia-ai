# Chat continuity, cancellation, observability, and frontend gates

## Goal and scope

Make long legal conversations usable without carrying unverified text forward, make Cancel stop provider work, expose mode-specific request health, and enforce the frontend test suites in CI. Existing user changes in the working tree are outside this design and must be preserved.

## Conversation continuity

Store one structured summary per conversation, keyed by conversation ID, with a schema version, the highest summarized message sequence, active topic, concise user facts, cited document and article identifiers, and source message IDs. Build it only from completed, cited, guardrail-approved turns. Redact personal data and secrets before persistence. Use a bounded size and deterministic update so summarization itself requires no provider call or extra tokens.

Keep the newest two eligible turns verbatim in the generation prompt. For referential follow-ups, combine those turns with the summary of older coherent turns. A clear new topic resets the active summary context; an ambiguous reference with multiple plausible topics asks for clarification rather than choosing silently. The current question determines answer language, even when earlier turns use the other language. Summary ownership follows the existing conversation ownership transfer at login, with no cross-conversation or cross-user sharing. A summary is navigation context only: every answer must still be grounded in freshly retrieved official citations. Ignore failed, cancelled, refused, uncited, and stale turns.

## Cancellation and quota

Propagate browser cancellation through the streaming route to the active provider HTTP connection. Replace thread-only cancellation at the provider boundary with a cancellable request path, including retry and verification calls. Check cancellation before each stage, provider attempt, and retry backoff. Close the provider response/client on cancellation and prevent a late worker result from storing an answer or emitting `done`.

Persist the user turn as `cancelled` and keep it ineligible for memory. Never persist a partial assistant answer. Settle the quota reservation exactly once: zero charge before provider start; after provider start charge only usage actually reported by the provider, without treating the full reservation as usage. If the provider reports no usage for a cancelled request, record unknown provider usage separately and release the local reservation. Provider billing may still occur before remote cancellation takes effect. Timeouts and disconnects retain distinct outcomes. Both explicit Cancel and a dropped client connection trigger cancellation.

## Observability

Record time from request acceptance to first status, first answer content, and completion; the first-content metric is absent for cancelled or failed requests without content. Record disconnect and explicit cancellation separately. Count provider attempts, retries, and failures at the provider boundary, including failures recovered by retry. Record prompt and completion tokens by reasoning mode (`fast`, `standard`, `deep`) and provider, with bounded labels and no user text. Add mode and outcome to request telemetry and durable observations. Avoid duplicate accounting between provider usage, quota settlement, and Prometheus metrics. Keep timings monotonic.

## Frontend quality gate

Logout retains the local session and returns a user-visible error on network failure or non-success response, including 503. A 401 can refresh and retry once; clear local state only after confirmed server-side logout. Add explicit frontend unit and integration test scripts over the existing Node test files, and make CI run lint, build, both test suites, and Playwright. Playwright uses its existing local test server and Chromium project. Run browser tests for this request because the user explicitly requested them; subsequent browser testing follows the user's standing preference.

## Verification

Add focused tests for long conversations, topic switch, ambiguous references, bilingual follow-ups, login ownership transfer, cancellation before and during provider work, absent partial answer, exact-once quota settlement, and metric labels/outcomes. Reproduce and fix the logout failure first. Run backend lint and relevant unit/integration tests, then frontend lint, build, unit, integration, and Playwright. Report any environment-dependent gate that cannot run locally; CI must still define it as required.

## Rollout and failure handling

Add an additive database migration for summary and observation fields. Existing conversations have no summary until new completed turns are processed; recent-turn behavior continues in the meantime. Invalid or outdated summaries are discarded and rebuilt from eligible messages. Cancellation cleanup must be idempotent when disconnect and explicit cancellation race. If provider cancellation itself fails, do not store the answer, record that failure, and release only unmeasured local reservation.
