"""Tests du MCPClient stdio via fake_mcp_server.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from jarvis_tools.mcp_client import MCPClient, MCPClientError
from jarvis_tools.mcp_registry import MCPServerConfig

FAKE_SERVER = Path(__file__).parent / "fake_mcp_server.py"


def _config(*extra_args: str) -> MCPServerConfig:
    return MCPServerConfig(
        name="fake",
        command=sys.executable,
        args=(str(FAKE_SERVER), *extra_args),
    )


def test_start_and_list_tools() -> None:
    with MCPClient(_config()) as client:
        tools = client.list_tools()
    names = sorted(t.name for t in tools)
    assert names == ["add", "echo"]


def test_call_tool_echo() -> None:
    with MCPClient(_config()) as client:
        result = client.call_tool("echo", {"text": "hello jarvis"})
    assert result.ok is True
    assert result.text() == "hello jarvis"


def test_call_tool_add() -> None:
    with MCPClient(_config()) as client:
        result = client.call_tool("add", {"a": 3, "b": 4})
    assert result.ok is True
    assert result.text() == "7.0"


def test_call_tool_unknown_returns_jsonrpc_error() -> None:
    with MCPClient(_config()) as client:
        result = client.call_tool("nope", {})
    assert result.ok is False
    assert result.error and "unknown tool" in result.error


def test_call_tool_is_error_propagates() -> None:
    with MCPClient(_config("--crash-on-call", "echo")) as client:
        result = client.call_tool("echo", {"text": "anything"})
    assert result.ok is False
    assert result.content[0]["text"] == "boom"


def test_timeout_when_server_doesnt_respond() -> None:
    # 2s pour éviter le flake en CI Linux (machine plus lente que dev local)
    client = MCPClient(_config("--raise-on-call", "echo"), request_timeout_sec=2.0)
    client.start()
    try:
        result = client.call_tool("echo", {"text": "never coming back"})
        # Le call_tool catche MCPClientError et renvoie ok=False
        assert result.ok is False
        assert result.error and "timeout" in result.error
    finally:
        client.close()


def test_call_without_start_raises() -> None:
    client = MCPClient(_config())
    with pytest.raises(MCPClientError, match="non démarré"):
        client.list_tools()


def test_start_fails_for_nonexistent_command() -> None:
    bad = MCPServerConfig(name="bad", command="this-binary-does-not-exist-xyz")
    client = MCPClient(bad)
    with pytest.raises(MCPClientError, match="impossible de lancer"):
        client.start()


def test_close_is_idempotent() -> None:
    client = MCPClient(_config())
    client.start()
    client.close()
    client.close()  # ne doit pas crasher
