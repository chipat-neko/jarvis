"""Toolbox : orchestre registry + clients MCP + proxy safety.

C'est le point d'entrée haut niveau pour le service jarvis-tools :
- charge la config (MCPRegistry)
- démarre les clients MCP enabled
- expose `list_all_tools()` et `call(server, tool, args)` à travers le ToolProxy
- garde un mapping tool_name → server (pour le tool calling LLM qui voit une
  liste plate de tools et qui doit savoir vers quel server router)
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_tools.mcp_client import MCPClient, MCPClientError, MCPTool, MCPToolResult
from jarvis_tools.mcp_registry import MCPRegistry, MCPServerConfig
from jarvis_tools.tool_proxy import ProxiedToolResult, ToolProxy, ToolProxyConfig


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """Un tool exposé par Toolbox (un MCPTool + son server d'origine)."""

    server: str
    tool: MCPTool

    @property
    def qualified_name(self) -> str:
        """`{server}.{tool}` — l'identifiant unique côté LlmRouter."""
        return f"{self.server}.{self.tool.name}"


class Toolbox:
    """Gestionnaire haut niveau des MCP servers.

    Args:
        registry: liste des MCP servers configurés.
        proxy_config: config safety appliquée à TOUS les appels.
        client_factory: optionnel, hook de test pour injecter des fakes
            (par défaut `MCPClient`).
    """

    def __init__(
        self,
        registry: MCPRegistry,
        *,
        proxy_config: ToolProxyConfig | None = None,
        client_factory=None,
    ) -> None:
        self._registry = registry
        self._proxy_cfg = proxy_config or ToolProxyConfig()
        self._client_factory = client_factory or MCPClient
        self._clients: dict[str, MCPClient] = {}
        self._tools_by_server: dict[str, list[MCPTool]] = {}
        self._proxies_by_server: dict[str, ToolProxy] = {}

    # ----- Lifecycle -----

    def start(self) -> dict[str, str | None]:
        """Démarre tous les MCP servers enabled. Retourne {name: error_or_None}.

        On ne lève PAS d'exception si un server échoue à démarrer — on continue
        avec les autres et on rapporte l'erreur dans le dict retourné. Permet
        au caller (gRPC server) de logger les ratés sans crasher tout le service.
        """
        results: dict[str, str | None] = {}
        for cfg in self._registry.enabled_servers():
            results[cfg.name] = self._start_one(cfg)
        return results

    def _start_one(self, cfg: MCPServerConfig) -> str | None:
        try:
            client = self._client_factory(cfg)
            client.start()
            tools = client.list_tools()
        except MCPClientError as exc:
            return str(exc)
        self._clients[cfg.name] = client
        self._tools_by_server[cfg.name] = tools
        self._proxies_by_server[cfg.name] = ToolProxy(
            self._make_tool_callable(cfg.name),
            config=self._proxy_cfg,
        )
        return None

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()
        self._tools_by_server.clear()
        self._proxies_by_server.clear()

    def __enter__(self) -> Toolbox:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ----- Discovery -----

    def list_all_tools(self) -> list[ToolDescriptor]:
        """Liste plate de tous les tools dispos, avec leur server d'origine."""
        out: list[ToolDescriptor] = []
        for server_name, tools in self._tools_by_server.items():
            for t in tools:
                out.append(ToolDescriptor(server=server_name, tool=t))
        return out

    def active_servers(self) -> tuple[str, ...]:
        return tuple(self._clients.keys())

    # ----- Calls -----

    def call(self, server: str, tool: str, arguments: dict | None = None) -> ProxiedToolResult:
        """Route un appel vers le bon server, à travers le ToolProxy."""
        proxy = self._proxies_by_server.get(server)
        if proxy is None:
            return ProxiedToolResult(
                ok=False,
                reason=f"server '{server}' non démarré ou inconnu",
            )
        return proxy.call(tool, arguments)

    def call_qualified(
        self, qualified_name: str, arguments: dict | None = None
    ) -> ProxiedToolResult:
        """Route un appel via un nom `{server}.{tool}` (forme LlmRouter)."""
        if "." not in qualified_name:
            return ProxiedToolResult(
                ok=False,
                reason=f"nom qualifié invalide: '{qualified_name}' (attendu 'server.tool')",
            )
        server, _, tool = qualified_name.partition(".")
        return self.call(server, tool, arguments)

    def _make_tool_callable(self, server_name: str):
        """Crée le callable bas-niveau passé au ToolProxy pour ce server."""

        def _do_call(tool_name: str, args: dict) -> MCPToolResult:
            client = self._clients.get(server_name)
            if client is None:
                return MCPToolResult(ok=False, error=f"client '{server_name}' indisponible")
            return client.call_tool(tool_name, args)

        return _do_call
