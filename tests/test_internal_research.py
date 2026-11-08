from fastapi.testclient import TestClient

from agent_workflows import internal_api
from agent_workflows.api import app

TENANT = "11111111-1111-4111-8111-111111111111"
KEY = "s" * 40


def test_internal_research_is_authenticated_tenant_bound_and_uses_rag_and_mcp(monkeypatch):
    monkeypatch.setenv("ATLAS_AGENT_SERVICE_KEY", KEY)
    monkeypatch.setenv("ATLAS_AGENT_TENANT_ID", TENANT)
    calls = []

    def fake_graph(question):
        calls.append(("rag", question))
        return {"status": "reviewed", "approved": True,
                "findings": [{"source": "guide.md", "chunk_id": "1", "observation": "Use TLS"}],
                "duration_ms": 2, "trace": []}

    async def fake_mcp(steps):
        calls.append(("mcp", steps[0]["tool"]))
        return {"engine": "mcp-planned", "status": "completed", "results": {"count": {"words": 2}},
                "trace": [], "duration_ms": 3, "tool_calls": 1, "llm_calls": 0}

    monkeypatch.setattr(internal_api, "run_graph", fake_graph)
    monkeypatch.setattr(internal_api, "run_mcp_plan", fake_mcp)
    client = TestClient(app)
    payload = {"question": "Use TLS", "tenant_id": TENANT, "workflow": "research"}
    url = "/internal/v1/execute"
    assert client.post(url, json=payload).status_code == 401
    headers = {"x-atlas-service-key": KEY}
    assert client.post(url, json={**payload, "tenant_id": "other"}, headers=headers).status_code == 403
    response = client.post(url, json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["research"]["findings"][0]["source"] == "guide.md"
    assert response.json()["duration_ms"] == 5
    assert calls == [("rag", "Use TLS"), ("mcp", "word_count")]


def test_research_rejects_llm_planner_without_running_tools(monkeypatch):
    monkeypatch.setenv("ATLAS_AGENT_SERVICE_KEY", KEY)
    monkeypatch.setenv("ATLAS_AGENT_TENANT_ID", TENANT)
    response = TestClient(app).post("/internal/v1/execute",
        json={"question": "hello", "tenant_id": TENANT, "workflow": "research", "planner": "llm"},
        headers={"x-atlas-service-key": KEY})
    assert response.status_code == 422
