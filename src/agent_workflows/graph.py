"""LangGraph orchestration with explicit stage boundaries and provenance."""
from __future__ import annotations

from time import perf_counter
from typing import Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from .atlas import atlas_search


class AgentState(TypedDict, total=False):
    question: str
    evidence: list[dict]
    tasks: list[str]
    findings: list[dict]
    approved: bool
    outcome: str
    trace: list[dict]


def build_graph(retriever: Callable[[str], list[dict]] | None = None):
    search = retriever or atlas_search

    def timed(name: str, handler: Callable[[AgentState], dict]):
        def node(state: AgentState) -> dict:
            start = perf_counter()
            output = handler(state)
            return {**output, "trace": [
                *state.get("trace", []),
                {"stage": name, "status": "completed", "duration_ms": round((perf_counter() - start) * 1000, 2)},
            ]}
        return node

    def plan(state: AgentState):
        return {"tasks": ["retrieve", "analyze", "review"]}

    def research(state: AgentState):
        hits = search(state["question"])
        if not isinstance(hits, list) or len(hits) > 10:
            raise ValueError("Retriever exceeded evidence bounds")
        if any(not isinstance(hit, dict) or not isinstance(hit.get("source"), str)
               or not isinstance(hit.get("text"), str)
               or len(hit["source"]) > 256 or len(hit["text"]) > 4000 for hit in hits):
            raise ValueError("Invalid retrieved evidence")
        return {"evidence": hits}

    def analyze(state: AgentState):
        # Deliberately evidence-preserving, not an LLM-generated conclusion.
        return {"findings": [
            {"source": item["source"], "observation": item["text"],
             "chunk_id": item.get("chunk_id")}
            for item in state["evidence"]
        ]}

    def review(state: AgentState):
        findings = state["findings"]
        approved = bool(findings) and all(item.get("source") and item.get("observation") for item in findings)
        return {"approved": approved, "outcome": "reviewed" if approved else "insufficient_evidence"}

    builder = StateGraph(AgentState)
    for name, handler in (
        ("planner", plan), ("researcher", research), ("analyst", analyze), ("reviewer", review)
    ):
        builder.add_node(name, timed(name, handler))
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "analyst")
    builder.add_edge("analyst", "reviewer")
    builder.add_edge("reviewer", END)
    return builder.compile()


def run_graph(question: str, *, retriever: Callable[[str], list[dict]] | None = None) -> dict:
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError("Question must have 1..2000 characters")
    started = perf_counter()
    result = build_graph(retriever).invoke({"question": question.strip(), "trace": [], "evidence": []})
    return {
        "run_id": str(uuid4()), "status": result["outcome"], "question": result["question"],
        "findings": result["findings"], "approved": result["approved"],
        "trace": result["trace"], "duration_ms": round((perf_counter() - started) * 1000, 2),
        "engine": "langgraph",
    }
