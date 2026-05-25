"""Tests du Toolbox : lifecycle + dispatch + safety."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from jarvis_tools.mcp_client import MCPClient, MCPTool, MCPToolResult
from jarvis_tools.mcp_registry import MCPRegistry, MCPServerConfig
from jarvis_tools.toolbox import Toolbox

FAKE_SERVER = Path(__file__).parent / "fake_mcp_server.py"


def _registry_with_fake() -> MCPRegistry:
    return MCPRegistry(
        servers=(
            MCPServerConfig(
                name="fake",
                command=sys.executable,
                args=(str(FAKE_SERVER),),
                enabled=True,
            ),
        )
    )


def _registry_with_disabled() -> MCPRegistry:
    return MCPRegistry(servers=(MCPServerConfig(name="off", command="anything", enabled=False),))


def test_toolbox_starts_and_lists_tools() -> None:
    with Toolbox(_registry_with_fake()) as tb:
        descriptors = tb.list_all_tools()
    names = sorted(d.qualified_name for d in descriptors)
    assert names == ["fake.add", "fake.echo"]


def test_toolbox_active_servers() -> None:
    with Toolbox(_registry_with_fake()) as tb:
        assert tb.active_servers() == ("fake",)


def test_toolbox_skips_disabled_servers() -> None:
    with Toolbox(_registry_with_disabled()) as tb:
        assert tb.active_servers() == ()
        assert tb.list_all_tools() == []


def test_toolbox_call_qualified() -> None:
    with Toolbox(_registry_with_fake()) as tb:
        res = tb.call_qualified("fake.echo", {"text": "hi"})
    assert res.ok is True
    assert res.result is not None and res.result.text() == "hi"


def test_toolbox_call_unknown_server_returns_failure() -> None:
    with Toolbox(_registry_with_fake()) as tb:
        res = tb.call("nope", "anything", {})
    assert res.ok is False
    assert "non démarré" in (res.reason or "")


def test_toolbox_call_qualified_malformed() -> None:
    with Toolbox(_registry_with_fake()) as tb:
        res = tb.call_qualified("missing-dot", {})
    assert res.ok is False
    assert "qualifié invalide" in (res.reason or "")


def test_toolbox_reports_startup_errors_without_raising() -> None:
    bad_registry = MCPRegistry(
        servers=(MCPServerConfig(name="ghost", command="this-does-not-exist-xyz", enabled=True),)
    )
    tb = Toolbox(bad_registry)
    results = tb.start()
    try:
        assert "ghost" in results
        assert results["ghost"] is not None and "impossible" in results["ghost"]
        # Server n'a pas été enregistré comme actif
        assert tb.active_servers() == ()
    finally:
        tb.close()


def test_toolbox_uses_client_factory() -> None:
    """Hook client_factory permet d'injecter un fake client (sans subprocess)."""
    fake_client = MagicMock(spec=MCPClient)
    fake_client.list_tools.return_value = [MCPTool(name="ping", description="pong")]
    fake_client.call_tool.return_value = MCPToolResult(
        ok=True, content=[{"type": "text", "text": "pong!"}]
    )

    def factory(cfg: MCPServerConfig) -> MagicMock:
        return fake_client

    registry = MCPRegistry(servers=(MCPServerConfig(name="x", command="ignored", enabled=True),))
    with Toolbox(registry, client_factory=factory) as tb:
        descriptors = tb.list_all_tools()
        res = tb.call("x", "ping", {})
    assert [d.qualified_name for d in descriptors] == ["x.ping"]
    assert res.ok is True
    assert res.result is not None and res.result.text() == "pong!"
    fake_client.start.assert_called_once()
    fake_client.close.assert_called_once()
