# Agent workflow v1

This is a deterministic, synchronous **local-only demonstration**, not an LLM multi-agent system yet.

## Stages

1. Planner: produces a fixed task plan.
2. Researcher: accepts only evidence supplied by the caller; does not search the web or ATLAS.
3. Analyst: maps supplied evidence into source-attributed observations.
4. Reviewer: marks the result reviewed when evidence-backed findings exist; otherwise insufficient_evidence.

Each execution returns a unique run ID, per-stage durations, total duration and review outcome. It does **not** persist runs, run stages in parallel, or call LLM providers.

## Local execution

```bash
pip install -e '.[dev]'
pytest -q tests/test_agent_workflows.py
uvicorn agent_workflows.api:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/v1/workflows/run \
  -H 'content-type: application/json' \
  -d '{"question":"What is the backup policy?","evidence":[{"source":"ops.md","text":"Backups run daily."}]}'
```

Or `docker compose -f compose.agent-demo.yml up --build` (port 8090).

## Security and next milestones

The demo endpoint is unauthenticated and must never be published to the internet.
Next: integrate a tenant-bound ATLAS RAG adapter; introduce a real LLM provider and LangGraph state graph;
add persistent checkpoints, authenticated asynchronous runs, retries, token/cost budgets, and distributed tracing.
Do not confuse these future milestones with delivered capabilities.
