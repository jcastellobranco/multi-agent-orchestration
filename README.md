# Multi-Agent Orchestration

Standalone **local-development** workflow with FastAPI, LangGraph, an optional server-side ATLAS RAG adapter, and per-stage traces.

> **Status:** The graph nodes are deterministic. This is **not** a production multi-agent/LLM system. There are no LLM-driven decisions, durable checkpoints, retries, authentication or async workers yet. Never publish the demo API.

## Prerequisites

- Git, Docker Engine and Docker Compose plugin (recommended), or Python 3.11+
- Optional: a running ATLAS RAG service for the LangGraph retrieval endpoint
- No model API key is required for the offline demonstration

## Quick start — Docker (offline demo)

```bash
git clone https://github.com/jcastellobranco/multi-agent-orchestration.git
cd multi-agent-orchestration
cp .env.example .env
docker compose -f compose.agent-demo.yml up --build -d
docker compose -f compose.agent-demo.yml ps
```

API documentation: http://127.0.0.1:8090/docs

Verify the service:

```bash
curl http://127.0.0.1:8090/health/live
```

Run the **offline** workflow with caller-supplied evidence (no ATLAS needed):

```bash
curl -sS -X POST http://127.0.0.1:8090/v1/workflows/run \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the backup policy?","evidence":[{"source":"ops.md","text":"Backups run daily."}]}'
```

Expected shape: `run_id`, `status: reviewed`, `approved: true`, `findings`, `trace` and `duration_ms`. A request without evidence returns `insufficient_evidence`, not invented findings.

Stop without deleting data:

```bash
docker compose -f compose.agent-demo.yml down
```

## Python development (without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
uvicorn agent_workflows.api:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

## ATLAS RAG integration (optional)

The `POST /v1/graphs/run` endpoint invokes the LangGraph graph and retrieves evidence from the **RAG service** `POST /v1/search`, not from the ATLAS frontend or authenticated BFF.

Configure the server's `.env`:

```dotenv
ATLAS_RAG_URL=http://127.0.0.1:8001
ATLAS_RAG_API_KEY=your-local-rag-service-key
ATLAS_TENANT_ID=11111111-1111-4111-8111-111111111111
```

The URL above is an **example**; port 8001 is not published by the standard ATLAS integrated Compose. If running the agent service in Docker, `127.0.0.1` refers to the agent container, **not your host**. Put both containers on a shared private Docker network and use `http://rag:8000`, or configure a suitable reachable host address. Do not expose RAG publicly just to connect these services.

After connectivity and credentials are configured, restart the agent service and invoke:

```bash
curl -sS -X POST http://127.0.0.1:8090/v1/graphs/run \
  -H 'Content-Type: application/json' \
  -d '{"question":"What does the document say about backups?"}'
```

Expected result includes `engine: langgraph`, source-backed findings, status and trace. This endpoint fails with 503 if the RAG configuration is missing and 502 if upstream retrieval fails. The RAG adapter requires an exact tenant UUID configured server-side.

## Planned execution prototype (new)

A separate **declarative DAG executor** is available at `POST /v1/plans/run`. It validates a bounded plan, executes independent steps concurrently, checks server-side scopes, and reports per-step timings. It currently uses **two local deterministic demo tools**, not a live MCP connection or LLM-generated plan.

For local Python development:

```bash
export DEMO_TOOL_SCOPES=text:read,text:hash
uvicorn agent_workflows.api:app --host 127.0.0.1 --port 8000
```

Then:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/plans/run \
  -H 'Content-Type: application/json' \
  -d '{"steps":[{"id":"count","tool":"text.word_count","args":{"text":"hello world"}},{"id":"hash","tool":"text.sha256","args":{"text":"hello world"}}]}'
```

The server denies all tools unless `DEMO_TOOL_SCOPES` is configured; callers **cannot** supply permissions. For Docker, pass that variable to the agent service in a local Compose override.

An offline microbenchmark compares sequential vs parallel independent I/O waits:

```bash
python scripts/benchmark_plans.py
```

This is **not yet** an A/B test of LLM agents: it makes zero LLM calls and does not use MCP transport. See [planned execution design, API and benchmark limits](docs/PLANNED_EXECUTION.md).

## Integrated planner → MCP execution (experimental)

This repository now includes a **real MCP stdio client** that launches the sibling `mcp-tool-platform` server, discovers its enabled tools, and invokes them through the MCP protocol. A bounded DAG executor handles dependencies and up to four concurrent calls per wave. An optional OpenAI-compatible LLM generates JSON plans, which are validated before execution.

**Prerequisites:** Both repositories must be checked out on the same machine, and the MCP server package must be installed in the Python environment used to launch it.

```bash
# In the multi-agent-orchestration checkout
python -m pip install -e '.[dev,mcp]'
# In the sibling MCP checkout (same virtual environment)
python -m pip install -e '../mcp-tool-platform[mcp]'
export MCP_TOOL_PROJECT_DIR="$(cd ../mcp-tool-platform && pwd)"
export MCP_ALLOWED_SCOPES=text:read,text:hash
uvicorn agent_workflows.api:app --host 127.0.0.1 --port 8000
```

Test the real MCP transport without a paid LLM:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/mcp-plans/run \
  -H 'Content-Type: application/json' \
  -d '{"question":"Count these words","planner":"offline"}'
```

The `offline` planner is intentionally simple: it constructs a single `word_count` step from the supplied question. It does not infer complex workflows.

For an optional LLM-generated plan, set these **server-side** environment variables before launching the API:

```bash
export PLANNER_API_URL=https://api.openai.com/v1
export PLANNER_API_KEY=your-api-key
export PLANNER_MODEL=your-json-compatible-model
```

Then send `{"question":"Count the words and hash this text: hello world","planner":"llm"}` to the same endpoint. The model must support chat completions and JSON-object responses. Model-generated plans are restricted to `word_count` and `sha256_text`, with bounded arguments and dependencies. Do not expose this unauthenticated local API to the internet.

**Current limits:** No durable checkpoints, retries, token-cost accounting, hybrid replan loop, public authentication or real-world side-effecting tools. The MCP bridge starts a local process per request. Its tool scopes are server-configured, not client-provided. The existing deterministic LangGraph and local DAG endpoints remain separate.

See [planned execution design](docs/PLANNED_EXECUTION.md).

## Tests and operational commands

```bash
python -m pytest -q
docker compose -f compose.agent-demo.yml logs -f agent-demo
docker compose -f compose.agent-demo.yml up -d --build --force-recreate
docker compose -f compose.agent-demo.yml down
```

For updates, run `git pull origin main` before rebuilding.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Port 8090 already allocated | Stop the other listener or change the left side of the Compose port mapping |
| `/v1/graphs/run` returns 503 | Set `ATLAS_RAG_URL`, `ATLAS_RAG_API_KEY` and `ATLAS_TENANT_ID` |
| `/v1/graphs/run` returns 502 | Check RAG container/network, service credentials and upstream logs |
| `rag` hostname not found | The agent container must share a Docker network with the RAG container |
| First ATLAS retrieval is slow | The RAG service may need to load/download its embedding model |
| Tests fail to import package | Install `-e '.[dev]'` in the active Python environment |

## Architecture and limits

```text
Client -> FastAPI /v1/graphs/run
       -> LangGraph planner -> researcher -> analyst -> reviewer
                                 |
                                 +-> ATLAS RAG /v1/search (private)
       <- run_id, outcome, findings, source/chunk references, stage trace
```

The reviewer currently checks whether evidence-backed findings exist; it does **not** verify factual correctness. The demo is synchronous and has no persisted run history.

See [workflow v1](docs/WORKFLOW_V1.md) and [agent engineering standards](AGENTS.md).

## Next milestones

- Structured LLM-backed agents and grounded citation verification
- PostgreSQL checkpointing, resume and idempotent retry semantics
- Authenticated tenant-bound asynchronous API and worker execution
- Token/cost budgets, rate limiting and distributed tracing
- ATLAS UI integration after standalone validation
