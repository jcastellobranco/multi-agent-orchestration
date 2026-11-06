"""Dependency-aware async orchestration with retry, timeout and audit trail."""
import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Awaitable, Callable

@dataclass(frozen=True)
class Step:
    name: str
    dependencies: tuple[str, ...]
    run: Callable[[dict], Awaitable[dict]]
    timeout: float = 10.0
    retries: int = 1

@dataclass
class RunRecord:
    results: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

class Orchestrator:
    def __init__(self, steps: list[Step]):
        self.steps = {s.name: s for s in steps}
        if len(self.steps) != len(steps):
            raise ValueError("Duplicate step")
        if any(s.timeout <= 0 or s.retries < 0 for s in steps):
            raise ValueError("Invalid timeout/retry settings")
        for step in steps:
            if any(dep not in self.steps for dep in step.dependencies):
                raise ValueError("Unknown dependency")
        self._order()

    def _order(self):
        ordered, visiting, visited = [], set(), set()
        def visit(name):
            if name in visiting:
                raise ValueError("Dependency cycle")
            if name in visited:
                return
            visiting.add(name)
            for dep in self.steps[name].dependencies:
                visit(dep)
            visiting.remove(name)
            visited.add(name)
            ordered.append(name)
        for name in self.steps:
            visit(name)
        return ordered

    async def execute(self, initial: dict | None = None) -> RunRecord:
        record = RunRecord(results=dict(initial or {}))
        for name in self._order():
            step = self.steps[name]
            for attempt in range(step.retries + 1):
                started = monotonic()
                try:
                    output = await asyncio.wait_for(step.run(dict(record.results)), step.timeout)
                    if not isinstance(output, dict):
                        raise TypeError("Step output must be dict")
                    record.results[name] = output
                    record.events.append({"step": name, "attempt": attempt + 1, "status": "ok", "elapsed_ms": round((monotonic()-started)*1000, 2)})
                    break
                except Exception as exc:
                    record.events.append({"step": name, "attempt": attempt + 1, "status": "error", "error": type(exc).__name__})
                    if attempt == step.retries:
                        raise RuntimeError(f"Step {name} failed after {attempt+1} attempts") from exc
                    await asyncio.sleep(min(0.1 * 2**attempt, 1))
        return record
