"""Test d'intégration : lance le vrai MCP filesystem via `npx -y`.

Skip si Node.js n'est pas dispo, ou si la variable d'environnement
`JARVIS_RUN_INTEGRATION=1` n'est pas posée (les tests d'intégration ne
tournent pas en CI par défaut car ils requièrent npm cache + réseau).

Pour lancer en local :
    set JARVIS_RUN_INTEGRATION=1
    pytest services/jarvis-tools/tests/test_integration_filesystem.py -v
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from jarvis_safety.rules.audit import AuditLogger
from jarvis_safety.rules.paths import PathWhitelist
from jarvis_tools.mcp_registry import MCPRegistry, MCPServerConfig
from jarvis_tools.tool_proxy import ToolProxyConfig
from jarvis_tools.toolbox import Toolbox

pytestmark = pytest.mark.skipif(
    os.environ.get("JARVIS_RUN_INTEGRATION") != "1"
    or shutil.which("npx") is None
    or shutil.which("npx.cmd") is None,
    reason="Intégration : nécessite npx + JARVIS_RUN_INTEGRATION=1",
)


def test_filesystem_mcp_list_tools(tmp_path: Path) -> None:
    """Lance @modelcontextprotocol/server-filesystem sur tmp_path et list les tools."""
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    assert npx is not None
    registry = MCPRegistry(
        servers=(
            MCPServerConfig(
                name="filesystem",
                command=npx,
                args=("-y", "@modelcontextprotocol/server-filesystem", str(tmp_path)),
                enabled=True,
            ),
        )
    )
    with Toolbox(registry) as tb:
        descriptors = tb.list_all_tools()
    names = {d.tool.name for d in descriptors}
    # Le server filesystem expose au moins ces tools (la liste exacte évolue)
    assert "read_file" in names or "read_text_file" in names
    assert any("write" in n for n in names) or any("list" in n for n in names)


def test_filesystem_mcp_read_with_proxy(tmp_path: Path) -> None:
    """Test E2E : écrit un fichier sous tmp_path, le relit via MCP + ToolProxy."""
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    assert npx is not None
    target = tmp_path / "hello.txt"
    target.write_text("contenu de test", encoding="utf-8")

    whitelist = PathWhitelist([str(tmp_path)])
    audit = AuditLogger(tmp_path / "audit.db")
    registry = MCPRegistry(
        servers=(
            MCPServerConfig(
                name="filesystem",
                command=npx,
                args=("-y", "@modelcontextprotocol/server-filesystem", str(tmp_path)),
                enabled=True,
            ),
        )
    )
    proxy_cfg = ToolProxyConfig(path_whitelist=whitelist, audit=audit)
    with Toolbox(registry, proxy_config=proxy_cfg) as tb:
        # Trouver le bon nom de tool (peut être read_file ou read_text_file)
        descriptors = tb.list_all_tools()
        read_tool = next(
            (d for d in descriptors if d.tool.name in {"read_file", "read_text_file"}),
            None,
        )
        assert read_tool is not None
        result = tb.call("filesystem", read_tool.tool.name, {"path": str(target)})

    assert result.ok is True, f"appel a échoué: {result.reason}"
    assert result.result is not None
    assert "contenu de test" in result.result.text()

    # Audit log : 2 events tool_call (before + after)
    events = audit.recent()
    assert len([e for e in events if e["action"] == "tool_call"]) >= 2


def test_filesystem_mcp_refused_outside_whitelist(tmp_path: Path) -> None:
    """ToolProxy refuse un read hors whitelist même si le MCP server l'autoriserait."""
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    assert npx is not None
    # Server filesystem ouvre tmp_path, mais ToolProxy whitelist plus restrictive
    restricted = tmp_path / "only_here"
    restricted.mkdir()
    elsewhere = tmp_path / "forbidden.txt"
    elsewhere.write_text("secret", encoding="utf-8")

    whitelist = PathWhitelist([str(restricted)])
    registry = MCPRegistry(
        servers=(
            MCPServerConfig(
                name="filesystem",
                command=npx,
                args=("-y", "@modelcontextprotocol/server-filesystem", str(tmp_path)),
                enabled=True,
            ),
        )
    )
    proxy_cfg = ToolProxyConfig(path_whitelist=whitelist)
    with Toolbox(registry, proxy_config=proxy_cfg) as tb:
        descriptors = tb.list_all_tools()
        read_tool = next(
            (d for d in descriptors if d.tool.name in {"read_file", "read_text_file"}),
            None,
        )
        assert read_tool is not None
        result = tb.call("filesystem", read_tool.tool.name, {"path": str(elsewhere)})

    assert result.refused is True
    assert "whitelist" in (result.reason or "").lower()
