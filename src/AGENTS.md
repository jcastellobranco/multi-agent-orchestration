# Agent workflow implementation instructions

Inherits repository root AGENTS.md.

- `agent_workflows/graph.py` owns LangGraph topology and state transitions; keep adapters outside the graph module.
- `agent_workflows/atlas.py` owns server-configured RAG access. Never pass tenant credentials through user input.
- `agent_workflows/api.py` is a local-only HTTP demo. Do not expose raw upstream exceptions.
- `agent_workflows/workflow.py` remains a deterministic baseline; avoid silently changing its public return contract.
- Keep node execution bounded; validate evidence sizes and preserve source/chunk IDs.
- Trace execution without logging sensitive source text.
- Add unit tests using injected/mock retrieval rather than depending on a live ATLAS deployment.
