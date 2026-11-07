import time
import pytest
from fastapi.testclient import TestClient
from agent_workflows.api import app
from agent_workflows.planned import execute_plan, run_demo_plan, PlanError, ExecutionError


def plan():
    return [
        {"id": "a", "tool": "text.word_count", "args": {"text": "two words"}},
        {"id": "b", "tool": "text.sha256", "args": {"text": "abc"}},
        {"id": "c", "tool": "text.word_count", "args": {"text": "three more words"}, "depends_on": ["a", "b"]},
    ]


def test_plan_and_trace():
    result = run_demo_plan(plan(), frozenset({"text:read", "text:hash"}))
    assert result["status"] == "completed"
    assert result["results"]["a"] == {"words": 2}
    assert [t["step"] for t in result["trace"]] == ["a", "b", "c"]
    assert result["tool_calls"] == 3
    assert result["llm_calls"] == 0


def test_denies_missing_scope_before_wave():
    with pytest.raises(PermissionError):
        run_demo_plan(plan(), frozenset({"text:read"}))


@pytest.mark.parametrize("bad", [
    [], [{"id": "a", "tool": "shell", "args": {}}],
    [{"id": "a", "tool": "text.word_count", "args": {}, "depends_on": ["a"]}],
    [{"id": "a", "tool": "text.word_count", "args": {}}, {"id": "a", "tool": "text.word_count", "args": {}}],
    [{"id": "a", "tool": "text.word_count", "args": {}, "unexpected": True}],
    [{"id": "a", "tool": "text.word_count", "args": {}, "depends_on": ["missing"]}],
])
def test_rejects_invalid_plans(bad):
    with pytest.raises(PlanError):
        run_demo_plan(bad, frozenset({"text:read", "text:hash"}))


def test_invalid_tool_input_is_safe_error():
    with pytest.raises(ExecutionError):
        run_demo_plan([{"id": "a", "tool": "text.word_count", "args": {"text": 3}}], frozenset({"text:read"}))


def test_parallel_ready_steps():
    def slow(_):
        time.sleep(.07)
        return {"ok": True}
    raw = [{"id": "a", "tool": "slow", "args": {}}, {"id": "b", "tool": "slow", "args": {}}]
    seq = execute_plan(raw, {"slow": slow}, authorize=lambda _: True, parallel=False)
    par = execute_plan(raw, {"slow": slow}, authorize=lambda _: True, parallel=True)
    assert seq["duration_ms"] > par["duration_ms"]


def test_http_demo_contract_and_policy(monkeypatch):
    monkeypatch.setenv("DEMO_TOOL_SCOPES", "text:read,text:hash")
    client = TestClient(app)
    response = client.post("/v1/plans/run", json={"steps": plan()})
    assert response.status_code == 200
    assert response.json()["results"]["a"]["words"] == 2
    monkeypatch.setenv("DEMO_TOOL_SCOPES", "text:read")
    denied = client.post("/v1/plans/run", json={"steps": plan()})
    assert denied.status_code == 403
    invalid = client.post("/v1/plans/run", json={"steps": [{"id": "x", "tool": "shell", "args": {}}]})
    assert invalid.status_code == 422
