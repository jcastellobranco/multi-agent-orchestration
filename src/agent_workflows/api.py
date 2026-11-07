"""Local development API; no authentication: never expose publicly."""
from fastapi import FastAPI
from pydantic import BaseModel, Field
from .workflow import run_workflow

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
