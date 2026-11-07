"""Bounded local MCP stdio bridge, one session per plan.

Only the trusted, explicitly configured sibling MCP server can be launched.
No user-provided executable, command, environment, or tool name is trusted.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from .planned import PlanError, ExecutionError, validate_plan

TOOL_SCOPES = {"word_count": "text:read", "sha256_text": "text:hash"}


def server_config() -> tuple[str, str, frozenset[str]]:
    path = os.getenv("MCP_TOOL_PROJECT_DIR", "").strip()
    if not path:
        raise RuntimeError("MCP_TOOL_PROJECT_DIR is not configured")
    root = Path(path).expanduser().resolve(strict=True)
    if not (root / "src" / "tool_platform" / "mcp_server.py").is_file():
        raise RuntimeError("MCP project path is invalid")
    raw = os.getenv("MCP_ALLOWED_SCOPES", "")
    scopes = frozenset(s.strip() for s in raw.split(",") if s.strip())
    if not scopes.issubset(TOOL_SCOPES.values()):
        raise RuntimeError("Invalid MCP scopes")
    return str(root), os.getenv("MCP_PYTHON", sys.executable), scopes


@asynccontextmanager
async def open_mcp():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root, python, scopes = server_config()
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONPATH"] = str(Path(root) / "src")
    env["MCP_ALLOWED_SCOPES"] = ",".join(sorted(scopes))
    params = StdioServerParameters(
        command=python, args=["-m", "tool_platform.mcp_server"], env=env,
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await asyncio.wait_for(session.initialize(), timeout=15)
            yield session, scopes


def decode_result(result) -> dict:
    if result.isError:
        raise ExecutionError("MCP tool reported failure")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        data = structured.get("result", structured)
    else:
        blocks = getattr(result, "content", [])
        if len(blocks) != 1 or getattr(blocks[0], "type", None) != "text":
            raise ExecutionError("Unsupported MCP result")
        try:
            data = json.loads(blocks[0].text)
        except (ValueError, TypeError) as exc:
            raise ExecutionError("Invalid MCP tool result") from exc
    if not isinstance(data, dict) or len(json.dumps(data)) > 12000:
        raise ExecutionError("Invalid or oversized MCP result")
    return data


async def run_mcp_plan(steps: list[dict], *, parallel: bool = True) -> dict:
    from time import perf_counter
    from uuid import uuid4

    started = perf_counter()
    async with open_mcp() as (session, scopes):
        catalog = await asyncio.wait_for(session.list_tools(), timeout=10)
        discovered = {tool.name for tool in catalog.tools}
        allowed = frozenset(
            name for name, scope in TOOL_SCOPES.items()
            if scope in scopes and name in discovered
        )
        plan = validate_plan(steps, allowed)
        results = {}
        trace = []
        pending = {step.id: step for step in plan}

        async def invoke(step):
            if TOOL_SCOPES[step.tool] not in scopes or step.tool not in discovered:
                raise PermissionError("Tool not authorized")
            tick = perf_counter()
            try:
                response = await asyncio.wait_for(
                    session.call_tool(step.tool, arguments=step.args), timeout=15,
                )
                return decode_result(response), round((perf_counter() - tick) * 1000, 2)
            except Exception as exc:
                raise ExecutionError("MCP tool invocation failed") from exc

        while pending:
            ready = [s for s in plan if s.id in pending and all(d in results for d in s.depends_on)]
            if not ready:
                raise PlanError("Unresolvable dependencies")
            if parallel:
                # Cap fan-out to four; calls share one initialized MCP session.
                outputs = []
                for offset in range(0, len(ready), 4):
                    outputs.extend(await asyncio.gather(*(invoke(s) for s in ready[offset:offset + 4])))
            else:
                outputs = [await invoke(s) for s in ready]
            for step, (output, duration) in zip(ready, outputs):
                results[step.id] = output
                trace.append({"step": step.id, "tool": step.tool, "duration_ms": duration, "status": "completed"})
                del pending[step.id]
        return {
            "run_id": str(uuid4()), "engine": "mcp-planned", "status": "completed",
            "results": results, "trace": trace, "tool_calls": len(plan),
            "llm_calls": 0, "duration_ms": round((perf_counter() - started) * 1000, 2),
        }
