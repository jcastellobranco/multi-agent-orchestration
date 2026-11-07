# Planned execution prototype

## What is implemented

A deterministic, bounded declarative DAG executor is exposed at `POST /v1/plans/run` for **trusted local development only**. It is separate from the existing LangGraph endpoint and has no LLM planning or real MCP network connection.

- Up to 12 steps with IDs, allowlisted tool names, static arguments and dependencies on **earlier** steps
- Up to 4 concurrent steps per dependency wave; dependent steps run only after prerequisites complete
- Authorization checked before every wave, using server-side `DEMO_TOOL_SCOPES` (default deny)
- Two pure demonstration tools: `text.word_count` and `text.sha256`
- Per-step execution timing, total duration and a run ID
- Bounded argument/output sizes and safe errors

The caller cannot provide scopes, register tools, submit arbitrary Python or interpolate previous outputs into arguments. The tool names are **local demo tools**, not an MCP server connection. There is no authentication, audit persistence, deadline/cancellation, retry or side-effect handling. Do not expose the API publicly.

## Start and call

```bash
export DEMO_TOOL_SCOPES=text:read,text:hash
uvicorn agent_workflows.api:app --host 127.0.0.1 --port 8000
```

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/plans/run \
  -H 'Content-Type: application/json' \
  -d '{"steps":[
    {"id":"count","tool":"text.word_count","args":{"text":"hello world"}},
    {"id":"hash","tool":"text.sha256","args":{"text":"hello world"}},
    {"id":"final","tool":"text.word_count","args":{"text":"done"},"depends_on":["count","hash"]}
  ]}'
```

A completed result contains `results`, `trace`, `duration_ms`, `tool_calls` and `llm_calls: 0`. The last field explicitly means this executor does **not** call a model.

For Docker, add `DEMO_TOOL_SCOPES=text:read,text:hash` to the agent service environment in your local Compose override, then rebuild/recreate it.

## Benchmark

```bash
python scripts/benchmark_plans.py
```

This compares sequential vs parallel execution of four independent simulated I/O waits, using 10 runs per mode. It is **not** a comparison of a traditional LLM agent loop against a generated-plan agent. It does not include model planning latency, MCP transport overhead, tokens, correctness or real tool calls. Do not cite the numbers as an AI-agent speedup.

## Next research milestone

Build a controlled A/B harness using the same model, tools and dataset for (a) sequential agent loop, (b) parallel-capable agent loop and (c) planned/hybrid executor. Measure end-to-end p50/p95, tokens, model calls, tool calls, correctness and cost. Add a policy-enforcing MCP adapter, verified authentication, persistence and cancellation before exposing real tools or side effects.
