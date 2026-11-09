"""Security regression tests for local-only demo routes."""
from fastapi.testclient import TestClient
from agent_workflows.api import app


def test_demo_routes_fail_closed(monkeypatch):
    monkeypatch.delenv("ATLAS_ENABLE_DEMO_ENDPOINTS", raising=False)
    with TestClient(app) as client:
        for path in ("/v1/workflows/run", "/v1/graphs/run", "/v1/plans/run", "/v1/mcp-plans/run"):
            response = client.post(path, json={})
            assert response.status_code == 404
        assert client.get("/health/live").status_code == 200


def test_demo_routes_require_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLE_DEMO_ENDPOINTS", "true")
    with TestClient(app) as client:
        response = client.post("/v1/workflows/run", json={"question": "hello", "evidence": []})
        assert response.status_code == 200


def test_internal_route_not_subject_to_demo_toggle(monkeypatch):
    monkeypatch.delenv("ATLAS_ENABLE_DEMO_ENDPOINTS", raising=False)
    with TestClient(app) as client:
        response = client.post("/internal/v1/execute", json={"question": "hello", "tenant_id": "test"})
        assert response.status_code in (401, 503)
