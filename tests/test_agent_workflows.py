from fastapi.testclient import TestClient
import pytest
from agent_workflows.api import app
from agent_workflows.workflow import run_workflow


def test_no_evidence_never_invents_findings():
    result = run_workflow("What are the risks?")
    assert result["status"] == "insufficient_evidence"
    assert result["findings"] == []
    assert [stage["stage"] for stage in result["trace"]] == [
        "planner", "researcher", "analyst", "reviewer"
    ]


def test_reviewed_findings_have_sources():
    result = run_workflow("What is documented?", [{"source": "manual.pdf", "text": "Backups are daily."}])
    assert result["approved"] is True
    assert result["findings"] == [{"source": "manual.pdf", "observation": "Backups are daily."}]
    assert all(stage["status"] == "completed" for stage in result["trace"])


def test_bounds():
    with pytest.raises(ValueError):
        run_workflow(" ")
    with pytest.raises(ValueError):
        run_workflow("ok", [{"source": "a", "text": "b"}] * 11)


def test_api_contract():
    client = TestClient(app)
    response = client.post("/v1/workflows/run", json={
        "question": "Summarize", "evidence": [{"source": "a.pdf", "text": "Evidence"}]
    })
    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"
    assert client.post("/v1/workflows/run", json={"question": ""}).status_code == 422
