from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
import sys
import asyncio
from agent_workflows import mcp_bridge


def test_mcp_child_does_not_inherit_secrets(monkeypatch):
    monkeypatch.setenv("ATLAS_AGENT_SERVICE_KEY", "sensitive")
    monkeypatch.setenv("GENERATION_API_KEY", "sensitive")
    monkeypatch.setenv("PYTHONSTARTUP", "/tmp/untrusted.py")
    monkeypatch.setattr(mcp_bridge, "server_config", lambda: ("/tmp/mcp", "python", frozenset({"text:read"})))
    captured = {}

    @asynccontextmanager
    async def fake_stdio(params):
        captured.update(params.env)
        yield object(), object()

    class FakeSession:
        def __init__(self, *_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def initialize(self): pass

    mcp = ModuleType("mcp")
    mcp.ClientSession = FakeSession
    mcp.StdioServerParameters = lambda **kw: SimpleNamespace(**kw)
    client = ModuleType("mcp.client")
    stdio = ModuleType("mcp.client.stdio")
    stdio.stdio_client = fake_stdio
    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", client)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", stdio)

    async def run():
        async with mcp_bridge.open_mcp():
            pass
    asyncio.run(run())
    assert captured["MCP_ALLOWED_SCOPES"] == "text:read"
    assert captured["PYTHONPATH"] == "/tmp/mcp/src"
    for key in ("ATLAS_AGENT_SERVICE_KEY", "GENERATION_API_KEY", "PYTHONSTARTUP"):
        assert key not in captured
