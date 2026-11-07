"""Server-side, single-tenant ATLAS RAG retrieval adapter.

The browser never supplies credentials or tenant identity.
"""
import os
from urllib.parse import urlsplit
from uuid import UUID
import httpx


class AtlasConfigurationError(RuntimeError):
    pass


def atlas_search(question: str, *, transport=None) -> list[dict]:
    url = os.getenv("ATLAS_RAG_URL", "").rstrip("/")
    key = os.getenv("ATLAS_RAG_API_KEY", "")
    tenant = os.getenv("ATLAS_TENANT_ID", "")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AtlasConfigurationError("Invalid ATLAS_RAG_URL")
    # Plain HTTP is permitted only for Docker/local private networking.
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "rag"):
        raise AtlasConfigurationError("HTTP RAG is permitted only for local Docker development")
    if not key or not tenant:
        raise AtlasConfigurationError("ATLAS_RAG_API_KEY and ATLAS_TENANT_ID are required")
    try:
        tenant = str(UUID(tenant))
    except ValueError as exc:
        raise AtlasConfigurationError("Invalid configured tenant UUID") from exc
    with httpx.Client(timeout=httpx.Timeout(10), transport=transport, trust_env=False) as client:
        response = client.post(
            f"{url}/v1/search",
            headers={"x-api-key": key, "x-tenant-id": tenant},
            json={"question": question, "limit": 5},
        )
        response.raise_for_status()
        body = response.json()
    hits = body.get("citations")
    if not isinstance(hits, list):
        raise ValueError("Invalid ATLAS retrieval response")
    evidence = []
    for hit in hits[:5]:
        if not isinstance(hit, dict) or any(not isinstance(hit.get(k), str) for k in ("source", "text", "chunk_id")):
            raise ValueError("Invalid ATLAS evidence item")
        evidence.append({"source": hit["source"][:256], "text": hit["text"][:4000], "chunk_id": hit["chunk_id"][:128]})
    return evidence
