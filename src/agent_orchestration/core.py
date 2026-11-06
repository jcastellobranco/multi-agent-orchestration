from dataclasses import dataclass, field
from typing import Callable

@dataclass
class Event:
    agent: str
    action: str
    outcome: str

@dataclass
class Context:
    request: str
    data: dict = field(default_factory=dict)
    audit: list[Event] = field(default_factory=list)

class Workflow:
    def __init__(self):
        self.steps: list[tuple[str, Callable[[Context], dict]]] = []

    def register(self, name: str, handler: Callable[[Context], dict]):
        if any(existing == name for existing, _ in self.steps):
            raise ValueError("Agent name must be unique")
        self.steps.append((name, handler))
        return self

    def run(self, request: str) -> Context:
        ctx = Context(request=request)
        for name, handler in self.steps:
            try:
                updates = handler(ctx)
                if not isinstance(updates, dict):
                    raise TypeError("Agent must return a dict")
                ctx.data.update(updates)
                ctx.audit.append(Event(name, "execute", "success"))
            except Exception as exc:
                ctx.audit.append(Event(name, "execute", "failed"))
                raise RuntimeError(f"Agent {name} failed") from exc
        return ctx

def example_workflow():
    return (Workflow()
            .register("planner", lambda c: {"plan": ["research", "summarize"]})
            .register("researcher", lambda c: {"evidence": c.request.strip().lower()})
            .register("reviewer", lambda c: {"approved": bool(c.data["evidence"])}))
