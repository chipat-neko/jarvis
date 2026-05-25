"""Fake MCP server pour les tests : lit JSON-RPC sur stdin, répond sur stdout.

Implémente le minimum (`initialize`, `tools/list`, `tools/call`) avec des
tools fictifs. Lancé via `subprocess.Popen([sys.executable, __file__, ...])`
par les tests.

CLI args optionnels :
  --crash-on-call NAME : retourne isError=true quand `NAME` est appelé
  --raise-on-call NAME : ne renvoie aucune réponse (simule un freeze) pour `NAME`
"""

from __future__ import annotations

import argparse
import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "Renvoie ce qu'on lui passe",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
        },
    },
    {
        "name": "add",
        "description": "Additionne a et b",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        },
    },
]


def _respond(req_id: int | None, *, result: dict | None = None, error: dict | None = None) -> None:
    msg: dict = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result or {}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crash-on-call", default=None)
    parser.add_argument("--raise-on-call", default=None)
    args = parser.parse_args(argv)

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            _respond(
                req_id,
                result={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp", "version": "0.0.1"},
                },
            )
        elif method == "tools/list":
            _respond(req_id, result={"tools": TOOLS})
        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            if name == args.raise_on_call:
                # Ne répond jamais → simule freeze (le client va timeout)
                continue
            if name == args.crash_on_call:
                _respond(
                    req_id,
                    result={"isError": True, "content": [{"type": "text", "text": "boom"}]},
                )
            elif name == "echo":
                _respond(
                    req_id,
                    result={
                        "isError": False,
                        "content": [{"type": "text", "text": str(arguments.get("text", ""))}],
                    },
                )
            elif name == "add":
                total = float(arguments.get("a", 0)) + float(arguments.get("b", 0))
                _respond(
                    req_id,
                    result={
                        "isError": False,
                        "content": [{"type": "text", "text": str(total)}],
                    },
                )
            else:
                _respond(req_id, error={"code": -32601, "message": f"unknown tool {name}"})
        else:
            _respond(req_id, error={"code": -32601, "message": f"unknown method {method}"})

    return 0


if __name__ == "__main__":
    sys.exit(main())
