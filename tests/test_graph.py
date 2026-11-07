import httpx
import pytest
from agent_workflows.graph import run_graph
from agent_workflows.atlas import atlas_search, AtlasConfigurationError


def test_langgraph_traces_and_provenance():
    result = run_graph("What are the requirements?", retriever=lambda question: [
        {"source": "guide.pdf", "chunk_id": "chunk-1", "text": "Use TLS."}
    ])
    assert result["engine"] == "langgraph"
    assert result["approved"] is True
    assert [item["stage"] for item in result["trace"]] == [
        "planner", "researcher", "analyst", "reviewer"
    ]
    assert result["findings"][0]["chunk_id"] == "chunk-1"


def test_langgraph_refuses_missing_evidence():
    result = run_graph("Unknown?", retriever=lambda _: [])
    assert result["status"] == "insufficient_evidence"
    assert result["findings"] == []


def test_atlas_adapter_binds_server_tenant(monkeypatch):
    tenant = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setenv("ATLAS_RAG_URL", "http://rag:8000")
    monkeypatch.setenv("ATLAS_RAG_API_KEY", "server-secret")
    monkeypatch.setenv("ATLAS_TENANT_ID", tenant)
    def handler(request):
        assert request.headers["x-tenant-id"] == tenant
        assert request.headers["x-api-key"] == "server-secret"
        return httpx.Response(200, json={"citations": [
            {"source": "guide.pdf", "chunk_id": "1", "text": "Use TLS."}
        ]})
    result = atlas_search("Question?", transport=httpx.MockTransport(handler))
    assert result[0]["source"] == "guide.pdf"


def test_atlas_adapter_rejects_untrusted_plain_http(monkeypatch):
    monkeypatch.setenv("ATLAS_RAG_URL", "http://example.com")
    with pytest.raises(AtlasConfigurationError):
        atlas_search("Question?")
