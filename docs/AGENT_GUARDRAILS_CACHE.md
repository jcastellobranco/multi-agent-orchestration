# Agent Guardrails, Cache and Telemetry

Implemented on the authenticated **/internal/v1/execute** path. Public demo routes are separate and are NOT protected by these new internal-only controls.

## Guardrails
- Question length and approximate token budget, conservative bounded evidence helper.
- Narrow prompt-injection heuristic blocks some explicit policy-override phrases. **Not a comprehensive prompt-injection defense**; untrusted retrieved documents still require policy isolation.
- Existing tool allowlist, per-invocation scopes, 12-step DAG, 4-way concurrency and 15-second MCP call timeout remain the security boundaries.
- Execution result validates maximum tool and LLM calls; side-effectful tools require a separate approval and idempotency design.
- The research workflow is evidence-preserving and does not independently verify factual entailment.

## Optional planner cache
Disabled by default. Enable only for low-sensitivity planner workloads:
```bash
ATLAS_PLANNER_CACHE_ENABLED=true
ATLAS_CACHE_HMAC_KEY=<unique-secret-at-least-32-characters>
ATLAS_PLANNER_CACHE_TTL_SECONDS=120
```
Cache keys are HMAC-SHA256 of tenant, prompt, model and policy version. Values are in-memory validated planner plans, **not** LLM answers or tool results. Max 128 entries per process; no Redis, no cross-worker invalidation, no persistence. Rotate key or restart workers on policy changes. Configure the secret through a secret manager, never commit it.

## Optional telemetry integration
```bash
ATLAS_EVAL_TELEMETRY_URL=https://your-evaluation-service
ATLAS_EVAL_TELEMETRY_KEY=<secret-from-secret-manager>
```
The agent sends only a run ID, hashed tenant, workflow, status, duration, tool/LLM call counts, cache hit and guardrail block to `POST /v1/telemetry/agent`. No prompts, tool arguments or results. The receiving service must deploy the matching telemetry branch and configure `EVAL_API_KEY`. HTTPS is required; telemetry is best-effort and never blocks execution on failure.

## Known gaps
No distributed Redis prompt cache, exact tokenizer, production-grade injection classifier, human approval workflow, per-tenant durable quota or distributed tracing yet. Do not claim production-ready guardrails.
