"""ATLAS internal service API. Never accept tenant identity from a browser."""
import os
from hmac import compare_digest

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .llm_planner import deterministic_plan, llm_plan
from .mcp_bridge import run_mcp_plan

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class InternalRun(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    tenant_id: str
    planner: str = Field(default="offline", pattern="^(offline|llm)$")

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
        steps = llm_plan(body.question) if body.planner == "llm" else deterministic_plan(body.question)
        result = await run_mcp_plan(steps)
        result["planner"] = body.planner
        result["llm_calls"] = 1 if body.planner == "llm" else 0
        return result
    except Exception:
        # Never leak tool output, upstream credentials or model exceptions.
        raise HTTPException(502, "Agent execution failed")
