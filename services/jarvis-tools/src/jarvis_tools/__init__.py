"""jarvis-tools : MCP integration (registry + client + safety proxy).

Layers :
- `mcp_registry` : config YAML déclarant les MCP servers (filesystem, brave, …)
- `mcp_client` : wrapper stdio JSON-RPC minimal (initialize / tools/list / tools/call)
- `tool_proxy` : applique les règles safety du Sprint A avant chaque CallTool

Le service expose ensuite ListTools + CallTool en gRPC (Phase 4 Sprint B).
"""

from jarvis_tools.mcp_client import MCPClient, MCPClientError, MCPTool, MCPToolResult
from jarvis_tools.mcp_registry import MCPRegistry, MCPServerConfig
from jarvis_tools.tool_proxy import ProxiedToolResult, ToolProxy, ToolProxyConfig
from jarvis_tools.toolbox import Toolbox, ToolDescriptor

__all__ = [
    "MCPClient",
    "MCPClientError",
    "MCPRegistry",
    "MCPServerConfig",
    "MCPTool",
    "MCPToolResult",
    "ProxiedToolResult",
    "ToolDescriptor",
    "ToolProxy",
    "ToolProxyConfig",
    "Toolbox",
]
