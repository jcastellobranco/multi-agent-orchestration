"""Deterministic four-stage workflow; provider integrations are intentionally separate."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Callable
from uuid import uuid4


class WorkflowError(RuntimeError):
    """A workflow stage failed; includes a safe stage name."""

    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"Workflow failed at stage: {stage}")


@dataclass(frozen=True)
class StageTrace:
    stage: str
    duration_ms: float
    status: str


def planner(state: dict) -> dict:
    return {"tasks": ["collect_evidence", "assess_evidence", "review_findings"]}


def researcher(state: dict) -> dict:
    # Explicitly no fabricated sources. A future ATLAS adapter supplies evidence.
    return {"evidence": list(state["evidence"])}


def analyst(state: dict) -> dict:
    evidence = state["evidence"]
    return {"findings": [
        {"source": item["source"], "observation": item["text"]}
        for item in evidence
    ]}


def reviewer(state: dict) -> dict:
    return {"approved": bool(state["findings"]),
            "outcome": "reviewed" if state["findings"] else "insufficient_evidence"}


STAGES: tuple[tuple[str, Callable[[dict], dict]], ...] = (
    ("planner", planner),
    ("researcher", researcher),
    ("analyst", analyst),
    ("reviewer", reviewer),
)


def run_workflow(question: str, evidence: list[dict] | None = None) -> dict:
    """Run bounded stages with trace; never expose exception text or invent evidence."""
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError("Question must have 1..2000 characters")
    sources = evidence if evidence is not None else []
    if not isinstance(sources, list) or len(sources) > 10 or any(
        not isinstance(item, dict)
        or not isinstance(item.get("source"), str)
        or not isinstance(item.get("text"), str)
        or len(item["source"]) > 256 or len(item["text"]) > 4000
        for item in sources
    ):
        raise ValueError("Evidence must contain at most 10 bounded source/text items")
    state = {"question": question.strip(), "evidence": sources}
    trace: list[StageTrace] = []
    started = perf_counter()
    for name, handler in STAGES:
        stage_started = perf_counter()
        try:
            output = handler(state)
            state.update(output)
        except Exception as exc:
            trace.append(StageTrace(name, round((perf_counter() - stage_started) * 1000, 2), "failed"))
            raise WorkflowError(name) from exc
        trace.append(StageTrace(name, round((perf_counter() - stage_started) * 1000, 2), "completed"))
    return {
        "run_id": str(uuid4()),
        "status": state["outcome"],
        "question": state["question"],
        "findings": state["findings"],
        "approved": state["approved"],
        "trace": [asdict(item) for item in trace],
        "duration_ms": round((perf_counter() - started) * 1000, 2),
    }
