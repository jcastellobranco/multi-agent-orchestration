import json
from types import SimpleNamespace
import httpx
import pytest

from agent_workflows.llm_planner import deterministic_plan, llm_plan
from agent_workflows.mcp_bridge import decode_result, server_config
from agent_workflows.planned import PlanError, ExecutionError


def test_offline_planner_is_explicit_and_bounded():
    assert deterministic_plan("hello")[0]["args"] == {"text": "hello"}
    with pytest.raises(PlanError):
        deterministic_plan("x" * 2001)


def test_llm_plan_validates_model_output(monkeypatch):
    monkeypatch.setenv("PLANNER_API_URL", "https://example.test/v1")
    monkeypatch.setenv("PLANNER_API_KEY", "secret")
    monkeypatch.setenv("PLANNER_MODEL", "mock")
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "steps": [{"id": "a", "tool": "word_count", "args": {"text": "hello"}}]
        })}}]})
    assert llm_plan("count", transport=httpx.MockTransport(handler))[0]["tool"] == "word_count"


def test_llm_plan_rejects_untrusted_tool(monkeypatch):
    monkeypatch.setenv("PLANNER_API_URL", "https://example.test/v1")
    monkeypatch.setenv("PLANNER_API_KEY", "secret")
    monkeypatch.setenv("PLANNER_MODEL", "mock")
    def handler(_):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "steps": [{"id": "x", "tool": "shell", "args": {"text": "bad"}}]
        })}}]})
    with pytest.raises(PlanError):
        llm_plan("run shell", transport=httpx.MockTransport(handler))


def test_mcp_response_decoding():
    result = SimpleNamespace(isError=False, structuredContent={"words": 2}, content=[])
    assert decode_result(result) == {"words": 2}
    result = SimpleNamespace(isError=False, structuredContent=None, content=[
        SimpleNamespace(type="text", text='{"words":2}')
    ])
    assert decode_result(result) == {"words": 2}
    with pytest.raises(ExecutionError):
        decode_result(SimpleNamespace(isError=True, structuredContent=None, content=[]))


def test_mcp_server_config_default_deny(monkeypatch, tmp_path):
    (tmp_path / "src" / "tool_platform").mkdir(parents=True)
    (tmp_path / "src" / "tool_platform" / "mcp_server.py").touch()
    monkeypatch.setenv("MCP_TOOL_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("MCP_ALLOWED_SCOPES", raising=False)
    assert server_config()[2] == frozenset()
    monkeypatch.setenv("MCP_ALLOWED_SCOPES", "text:read,text:hash")
    assert server_config()[2] == frozenset({"text:read", "text:hash"})
    monkeypatch.setenv("MCP_ALLOWED_SCOPES", "admin")
    with pytest.raises(RuntimeError):
        server_config()


def test_integrated_api_uses_server_bound_mcp(monkeypatch):
    from fastapi.testclient import TestClient
    from agent_workflows import api

    async def fake_run(steps, *, parallel=True):
        assert steps[0]["tool"] == "word_count"
        return {"engine": "mcp-planned", "status": "completed", "results": {"count": {"words": 2}}, "llm_calls": 0}

    monkeypatch.setattr(api, "run_mcp_plan", fake_run)
    response = TestClient(api.app).post("/v1/mcp-plans/run", json={"question": "hello world", "planner": "offline"})
    assert response.status_code == 200
    assert response.json()["planner"] == "offline"
    assert response.json()["llm_calls"] == 0
    assert TestClient(api.app).post("/v1/mcp-plans/run", json={"question": "hi", "planner": "unknown"}).status_code == 422


def test_integrated_api_never_exposes_upstream_errors(monkeypatch):
    from fastapi.testclient import TestClient
    from agent_workflows import api

    async def fake_run(steps, *, parallel=True):
        raise RuntimeError("private tool secret")

    monkeypatch.setattr(api, "run_mcp_plan", fake_run)
    response = TestClient(api.app).post("/v1/mcp-plans/run", json={"question": "hello"})
    assert response.status_code == 502
    assert "secret" not in response.text
