"""ATLAS internal service API. Never accept tenant identity from a browser."""
import os
import asyncio
from hmac import compare_digest

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .llm_planner import deterministic_plan, llm_plan
from .mcp_bridge import run_mcp_plan
from .graph import run_graph

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class InternalRun(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    tenant_id: str
    planner: str = Field(default="offline", pattern="^(offline|llm)$")
    workflow: str = Field(default="tools", pattern="^(tools|research)$")

    model_config = {"extra": "forbid"}


@router.post("/execute")
async def execute_internal(body: InternalRun, x_atlas_service_key: str | None = Header(default=None)):
    key = os.getenv("ATLAS_AGENT_SERVICE_KEY", "")
    tenant = os.getenv("ATLAS_AGENT_TENANT_ID", "")
    if len(key) < 32 or not tenant:
        raise HTTPException(503, "Internal service not configured")
    if not x_atlas_service_key or not compare_digest(x_atlas_service_key, key):
        raise HTTPException(401, "Unauthorized")
    if body.tenant_id != tenant:
        raise HTTPException(403, "Tenant not supported by this agent deployment")
    try:
        if body.workflow == "research":
            if body.planner != "offline":
                raise HTTPException(422, "Research workflow currently requires offline planning")
            # LangGraph uses the existing server-bound, tenant-scoped RAG adapter.
            # Run its synchronous HTTP retrieval outside the event loop.
            graph = await asyncio.to_thread(run_graph, body.question)
            # Keep MCP execution and its independent scope enforcement in the flow.
            steps = deterministic_plan(body.question)
            mcp = await run_mcp_plan(steps)
            return {
                **mcp, "workflow": "research", "planner": "offline",
                "llm_calls": 0, "research": graph,
                "status": "completed" if graph["approved"] else "insufficient_evidence",
                "duration_ms": round(graph["duration_ms"] + mcp["duration_ms"], 2),
            }
        steps = llm_plan(body.question) if body.planner == "llm" else deterministic_plan(body.question)
        result = await run_mcp_plan(steps)
        result["planner"] = body.planner
        result["llm_calls"] = 1 if body.planner == "llm" else 0
        return result
    except HTTPException:
        raise
    except Exception:
        # Never leak tool output, upstream credentials or model exceptions.
        raise HTTPException(502, "Agent execution failed")
