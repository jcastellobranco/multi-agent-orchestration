"""Bounded declarative workflow executor; no generated code or arbitrary tools.

This is a deterministic proof-of-concept. It compares tool orchestration
strategies, NOT LLM inference speed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import perf_counter
from typing import Callable
from uuid import uuid4

MAX_STEPS = 12
MAX_WORKERS = 4
MAX_OUTPUT_CHARS = 12000


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    args: dict
    depends_on: tuple[str, ...] = ()


class PlanError(ValueError):
    pass


class ExecutionError(RuntimeError):
    pass


def validate_plan(raw: list[dict], allowed_tools: frozenset[str]) -> list[Step]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_STEPS:
        raise PlanError("Plan must contain 1..12 steps")
    steps = []
    ids = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"id", "tool", "args", "depends_on"}:
            raise PlanError("Invalid step shape")
        sid, tool, args, deps = (item.get("id"), item.get("tool"), item.get("args"), item.get("depends_on", []))
        if not isinstance(sid, str) or not sid.isidentifier() or len(sid) > 48 or sid in ids:
            raise PlanError("Invalid or duplicate step id")
        if not isinstance(tool, str) or tool not in allowed_tools:
            raise PlanError("Tool is not allowlisted")
        if not isinstance(args, dict) or len(str(args)) > 4000:
            raise PlanError("Invalid tool arguments")
        if not isinstance(deps, list) or len(deps) > MAX_STEPS or any(
            not isinstance(d, str) or d not in ids for d in deps
        ) or len(set(deps)) != len(deps):
            raise PlanError("Dependencies must reference distinct earlier steps")
        ids.add(sid)
        steps.append(Step(sid, tool, args, tuple(deps)))
    return steps


def execute_plan(
    raw: list[dict],
    tools: dict[str, Callable[[dict], dict]],
    *,
    authorize: Callable[[str], bool] | None = None,
    parallel: bool = True,
) -> dict:
    """Execute bounded DAG. Tool callbacks must be side-effect-free/idempotent.

    Arguments are static; dependent outputs are not interpolated into arguments.
    The policy callback runs immediately before *each* invocation.
    """
    steps = validate_plan(raw, frozenset(tools))
    authorize = authorize or (lambda tool: False)  # fail closed
    started = perf_counter()
    results: dict[str, dict] = {}
    trace: list[dict] = []
    pending = {step.id: step for step in steps}
    while pending:
        ready = [s for s in steps if s.id in pending and all(d in results for d in s.depends_on)]
        if not ready:
            raise PlanError("Unresolvable dependencies")
        # Check permissions for entire wave before starting any work.
        for step in ready:
            if not authorize(step.tool):
                raise PermissionError("Tool execution not authorized")

        def invoke(step: Step):
            tick = perf_counter()
            try:
                output = tools[step.tool](dict(step.args))
                if not isinstance(output, dict) or len(str(output)) > MAX_OUTPUT_CHARS:
                    raise ExecutionError("Invalid or oversized tool result")
                return step.id, output, round((perf_counter() - tick) * 1000, 2)
            except Exception as exc:
                raise ExecutionError(f"Step {step.id} failed") from exc

        if parallel and len(ready) > 1:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(ready))) as pool:
                futures = {pool.submit(invoke, s): s for s in ready}
                wave = {}
                for future in as_completed(futures):
                    sid, output, duration = future.result()
                    wave[sid] = (output, duration)
        else:
            wave = {}
            for step in ready:
                sid, output, duration = invoke(step)
                wave[sid] = (output, duration)
        for step in ready:
            output, duration = wave[step.id]
            results[step.id] = output
            trace.append({"step": step.id, "tool": step.tool, "duration_ms": duration, "status": "completed"})
            del pending[step.id]
    return {
        "run_id": str(uuid4()), "engine": "planned", "status": "completed",
        "results": results, "trace": trace,
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "tool_calls": len(steps), "llm_calls": 0,
    }


def demo_tools() -> dict[str, Callable[[dict], dict]]:
    """Offline tools, intentionally pure and bounded."""
    import hashlib

    def read_text(args):
        if set(args) != {"text"} or not isinstance(args["text"], str) or len(args["text"]) > 2000:
            raise ValueError("Expected text <= 2000 chars")
        return {"words": len(args["text"].split())}

    def hash_text(args):
        if set(args) != {"text"} or not isinstance(args["text"], str) or len(args["text"]) > 2000:
            raise ValueError("Expected text <= 2000 chars")
        return {"sha256": hashlib.sha256(args["text"].encode()).hexdigest()}

    return {"text.word_count": read_text, "text.sha256": hash_text}


def run_demo_plan(raw: list[dict], scopes: frozenset[str]) -> dict:
    required = {"text.word_count": "text:read", "text.sha256": "text:hash"}
    return execute_plan(raw, demo_tools(), authorize=lambda tool: required[tool] in scopes)
