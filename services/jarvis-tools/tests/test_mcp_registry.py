"""Tests du registre MCP : load YAML + expansion env vars + filtres."""

from __future__ import annotations

from pathlib import Path

from jarvis_tools.mcp_registry import MCPRegistry, MCPServerConfig


def test_empty_registry() -> None:
    reg = MCPRegistry.empty()
    assert reg.servers == ()
    assert reg.enabled_servers() == ()
    assert reg.get("anything") is None


def test_from_yaml_missing_file_returns_empty(tmp_path: Path) -> None:
    reg = MCPRegistry.from_yaml(tmp_path / "does_not_exist.yaml")
    assert reg.servers == ()


def test_from_yaml_parses_servers(tmp_path: Path) -> None:
    yaml_file = tmp_path / "mcp.yaml"
    yaml_file.write_text(
        """
servers:
  filesystem:
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-filesystem"
      - "D:/assistant_ai"
    enabled: true
  brave-search:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-brave-search"]
    env:
      BRAVE_API_KEY: "$BRAVE_API_KEY"
    enabled: false
""",
        encoding="utf-8",
    )
    reg = MCPRegistry.from_yaml(yaml_file)
    assert len(reg.servers) == 2
    fs = reg.get("filesystem")
    assert fs is not None
    assert fs.command == "npx"
    assert fs.args == ("-y", "@modelcontextprotocol/server-filesystem", "D:/assistant_ai")
    assert fs.enabled is True

    brave = reg.get("brave-search")
    assert brave is not None
    assert brave.enabled is False
    assert brave.env == {"BRAVE_API_KEY": "$BRAVE_API_KEY"}


def test_enabled_servers_filters() -> None:
    reg = MCPRegistry(
        servers=(
            MCPServerConfig(name="a", command="x", enabled=True),
            MCPServerConfig(name="b", command="y", enabled=False),
            MCPServerConfig(name="c", command="z", enabled=True),
        )
    )
    enabled = reg.enabled_servers()
    assert {s.name for s in enabled} == {"a", "c"}


def test_resolved_env_substitutes_existing(monkeypatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret-value")
    cfg = MCPServerConfig(name="x", command="echo", env={"API": "$MY_KEY"})
    assert cfg.resolved_env() == {"API": "secret-value"}


def test_resolved_env_keeps_raw_if_missing(monkeypatch) -> None:
    monkeypatch.delenv("UNSET_VAR", raising=False)
    cfg = MCPServerConfig(name="x", command="echo", env={"API": "$UNSET_VAR"})
    assert cfg.resolved_env() == {"API": "$UNSET_VAR"}


def test_resolved_env_brace_form(monkeypatch) -> None:
    monkeypatch.setenv("FOO", "bar")
    cfg = MCPServerConfig(name="x", command="echo", env={"KEY": "${FOO}/path"})
    assert cfg.resolved_env() == {"KEY": "bar/path"}


def test_names_returns_all_in_order() -> None:
    reg = MCPRegistry(
        servers=(
            MCPServerConfig(name="z", command="x"),
            MCPServerConfig(name="a", command="x"),
        )
    )
    assert reg.names() == ("z", "a")
