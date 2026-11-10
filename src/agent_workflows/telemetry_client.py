"""Best-effort, opt-in delivery of redacted agent metrics to the evaluation service."""
import asyncio
import hashlib
import os
from urllib.parse import urlsplit
from uuid import uuid4

async def emit(tenant: str, workflow: str, result: dict, *, blocked: bool = False):
    url = os.getenv("ATLAS_EVAL_TELEMETRY_URL", "").rstrip("/")
    key = os.getenv("ATLAS_EVAL_TELEMETRY_KEY", "")
    if not url or not key:
        return
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
        return
    event = {
        "run_id": str(result.get("run_id") or uuid4()),
        "tenant_hash": hashlib.sha256(tenant.encode()).hexdigest(),
        "workflow": workflow,
        "status": "blocked" if blocked else result.get("status", "failed"),
        "duration_ms": max(0, float(result.get("end_to_end_ms", result.get("duration_ms", 0)))),
        "llm_calls": max(0, int(result.get("llm_calls", 0))),
        "tool_calls": max(0, int(result.get("tool_calls", 0))),
        "cache_hit": bool(result.get("cache_hit", False)),
        "guardrail_blocked": blocked,
    }
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            await client.post(f"{url}/v1/telemetry/agent", json=event,
                              headers={"x-api-key": key})
    except Exception:
        # Telemetry must never break or expose details of a business operation.
        return
