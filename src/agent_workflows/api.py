"""Local development API; no authentication: never expose publicly."""
from fastapi import FastAPI
from pydantic import BaseModel, Field
from .workflow import run_workflow
from .graph import run_graph
from .atlas import AtlasConfigurationError
from fastapi import HTTPException

app = FastAPI(title="Multi-Agent Orchestration (local demo)")


class Evidence(BaseModel):
    source: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=4000)


class WorkflowRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)


@app.get("/health/live")
def health():
    return {"status": "ok"}


@app.post("/v1/workflows/run")
def run(request: WorkflowRequest):
    return run_workflow(request.question, [item.model_dump() for item in request.evidence])


class GraphRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.post("/v1/graphs/run")
def execute_graph(request: GraphRequest):
    """Local-only synchronous graph; server-configured tenant and service key."""
    try:
        return run_graph(request.question)
    except AtlasConfigurationError:
        raise HTTPException(503, "ATLAS retrieval is not configured")
    except Exception:
        raise HTTPException(502, "Graph execution failed")


# Local-only declarative executor. Scope permissions are process configuration,
# NEVER accepted from the unauthenticated request body.
import os
from .planned import run_demo_plan, PlanError, ExecutionError


class PlanStepRequest(BaseModel):
    id: str = Field(min_length=1, max_length=48)
    tool: str = Field(min_length=1, max_length=80)
    args: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=12)

    model_config = {"extra": "forbid"}


class PlanRequest(BaseModel):
    steps: list[PlanStepRequest] = Field(min_length=1, max_length=12)

    model_config = {"extra": "forbid"}


@app.post("/v1/plans/run")
def execute_demo_plan(request: PlanRequest):
    """Synchronous offline demo; never publish this unauthenticated endpoint."""
    allowed = {"text:read", "text:hash"}
    scopes = frozenset(s.strip() for s in os.getenv("DEMO_TOOL_SCOPES", "").split(",") if s.strip())
    if not scopes.issubset(allowed):
        raise HTTPException(503, "Invalid server tool scope configuration")
    try:
        return run_demo_plan([step.model_dump() for step in request.steps], scopes)
    except PermissionError:
        raise HTTPException(403, "Tool execution not authorized")
    except PlanError:
        raise HTTPException(422, "Invalid execution plan")
    except ExecutionError:
        raise HTTPException(502, "Tool execution failed")
