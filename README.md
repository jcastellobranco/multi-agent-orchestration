# Multi-Agent Orchestration

A standalone, auditable LangGraph workflow with a server-bound adapter to ATLAS RAG.

## Implemented

- LangGraph four-node state graph: planner → researcher → analyst → reviewer
- HTTP adapter to ATLAS RAG `POST /v1/search` with server-configured API key and tenant UUID
- Per-stage execution trace, source/chunk provenance, explicit insufficient-evidence outcome
- Local FastAPI endpoints and deterministic tests with mocked retrieval
- Docker development image and GitHub Actions pytest

**Current limitation:** The nodes are deterministic orchestration stages, not autonomous LLM-powered agents. No persistence, retries, checkpoints, distributed tracing, parallel execution or production authentication is implemented. The Reviewer validates source presence, not factual truth. Do not deploy this demo publicly.

## Local start

```bash
pip install -e '.[dev]'
pytest -q
uvicorn agent_workflows.api:app --reload --host 127.0.0.1
```

`POST /v1/workflows/run` accepts explicit evidence and works offline. `POST /v1/graphs/run` uses the configured ATLAS RAG service.

For Docker demo: `docker compose -f compose.agent-demo.yml up --build` (binds only localhost:8090).

## ATLAS RAG integration

Configure **server-side** variables (never pass tenant or service key from the browser):

```dotenv
ATLAS_RAG_URL=http://rag:8000
ATLAS_RAG_API_KEY=your-rag-service-key
ATLAS_TENANT_ID=11111111-1111-4111-8111-111111111111
```

The URL must point to the **RAG service**, not the ATLAS frontend or JWT-protected BFF. `rag` is resolvable only when containers share the appropriate Docker network. For host development, use `http://127.0.0.1:<rag-published-port>`. The default compose file does not connect to ATLAS automatically. Only use the endpoint on a trusted development network.

## Roadmap

1. Provider-backed Planner/Analyst/Reviewer with strict structured outputs and citation checks.
2. Durable run storage and checkpoint/resume with PostgreSQL.
3. Authenticated async API, tenant isolation, quotas and budgets.
4. Worker execution, retry policy, per-node failure tracing and observability integration.
5. Integrate agent runs into the ATLAS UI after the standalone API is validated.

See [workflow v1](docs/WORKFLOW_V1.md) for the original deterministic demonstration.
