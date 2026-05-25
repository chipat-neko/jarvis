"""Client MCP minimal : stdio JSON-RPC.

Lance un MCP server en sous-process et échange des messages JSON-RPC sur
stdin/stdout. Implémente le sous-ensemble nécessaire au Sprint B :
- `initialize` (handshake)
- `tools/list`
- `tools/call`

Pas d'asyncio ici (subprocess.Popen + threads daemon pour le reader) → le
client reste compatible avec le LlmRouter actuel qui mélange sync et async.
La sérialisation utilise la lib `json` standard (un objet par ligne pour
matching simple).

Le protocole MCP officiel est plus riche (notifications, progress, sampling) —
on n'implémente que le strict minimum testable. La lib `mcp` officielle prendra
le relais si on a besoin de plus.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any

from jarvis_tools.mcp_registry import MCPServerConfig


@dataclass(frozen=True, slots=True)
class MCPTool:
    """Description d'un outil exposé par un MCP server."""

    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> MCPTool:
        return cls(
            name=str(d.get("name", "")),
            description=str(d.get("description", "")),
            input_schema=d.get("inputSchema") or d.get("input_schema") or {},
        )


@dataclass(frozen=True, slots=True)
class MCPToolResult:
    """Résultat d'un appel CallTool."""

    ok: bool
    content: list[dict] = field(default_factory=list)  # liste de blocs {type, text|...}
    error: str | None = None

    def text(self) -> str:
        """Concatène les blocs `text` du résultat pour un retour lisible."""
        parts: list[str] = []
        for block in self.content:
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)


class MCPClientError(RuntimeError):
    """Erreur générique du client MCP (subprocess down, timeout, JSON-RPC error)."""


class MCPClient:
    """Client stdio JSON-RPC vers un MCP server.

    Args:
        config: configuration du server (command + args + env).
        request_timeout_sec: timeout par requête (par défaut 30s).

    Lifecycle :
        client = MCPClient(config)
        client.start()       # spawn le subprocess + initialize
        tools = client.list_tools()
        result = client.call_tool("read_file", {"path": "..."})
        client.close()       # SIGTERM puis kill si besoin
    """

    JSONRPC_VERSION = "2.0"

    def __init__(self, config: MCPServerConfig, *, request_timeout_sec: float = 30.0) -> None:
        self.config = config
        self.request_timeout_sec = request_timeout_sec
        self._proc: subprocess.Popen[str] | None = None
        self._responses: Queue[dict] = Queue()
        self._next_id = 1
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None

    # ----- Lifecycle -----

    def start(self) -> None:
        if self._proc is not None:
            return
        env = os.environ.copy()
        env.update(self.config.resolved_env())
        try:
            self._proc = subprocess.Popen(
                [self.config.command, *self.config.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,  # line-buffered
            )
        except (OSError, FileNotFoundError) as exc:
            raise MCPClientError(f"impossible de lancer '{self.config.command}': {exc}") from exc

        self._reader_thread = threading.Thread(
            target=self._read_stdout,
            name=f"mcp-reader-{self.config.name}",
            daemon=True,
        )
        self._reader_thread.start()
        self._initialize()

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        finally:
            self._proc = None

    def __enter__(self) -> MCPClient:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ----- High-level RPCs -----

    def list_tools(self) -> list[MCPTool]:
        result = self._rpc("tools/list", {})
        tools_raw = (result or {}).get("tools", [])
        return [MCPTool.from_dict(t) for t in tools_raw]

    def call_tool(self, name: str, arguments: dict | None = None) -> MCPToolResult:
        params: dict[str, Any] = {"name": name, "arguments": arguments or {}}
        try:
            result = self._rpc("tools/call", params)
        except MCPClientError as exc:
            return MCPToolResult(ok=False, error=str(exc))
        if result is None:
            return MCPToolResult(ok=False, error="réponse vide")
        is_error = bool(result.get("isError", False))
        content = result.get("content", []) or []
        if is_error:
            return MCPToolResult(ok=False, content=content, error="server returned isError=true")
        return MCPToolResult(ok=True, content=content)

    # ----- Internals -----

    def _initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "jarvis-tools", "version": "0.1.0"},
            },
        )

    def _rpc(self, method: str, params: dict) -> dict | None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPClientError("client non démarré (appel start() d'abord)")
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
        request = {
            "jsonrpc": self.JSONRPC_VERSION,
            "id": req_id,
            "method": method,
            "params": params,
        }
        try:
            self._proc.stdin.write(json.dumps(request) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise MCPClientError(f"stdin fermé: {exc}") from exc

        deadline = time.monotonic() + self.request_timeout_sec
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPClientError(f"timeout {self.request_timeout_sec}s sur {method}")
            try:
                msg = self._responses.get(timeout=min(remaining, 0.5))
            except Empty:
                if self._proc.poll() is not None:
                    raise MCPClientError(
                        f"subprocess MCP '{self.config.name}' a quitté (rc={self._proc.returncode})"
                    ) from None
                continue
            if msg.get("id") != req_id:
                # message non-corrélé (notification, autre id) → on l'ignore
                continue
            if "error" in msg:
                err = msg["error"]
                raise MCPClientError(f"{method} a échoué: {err}")
            return msg.get("result")

    def _read_stdout(self) -> None:
        if self._proc is None or self._proc.stdout is None:
            return
        for raw_line in self._proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                self._responses.put(msg)
