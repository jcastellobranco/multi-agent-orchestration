import asyncio
import pytest
from agent_orchestration.advanced import Orchestrator, Step
def test_dependency_order():
    async def run_a(ctx): return {"value":1}
    async def run_b(ctx): return {"previous":ctx["a"]["value"]}
    orch=Orchestrator([Step("b",("a",),run_b),Step("a",(),run_a)])
    result=asyncio.run(orch.execute())
    assert result.results["b"]["previous"]==1
def test_cycle():
    async def noop(ctx): return {}
    with pytest.raises(ValueError):
        Orchestrator([Step("a",("b",),noop),Step("b",("a",),noop)])
