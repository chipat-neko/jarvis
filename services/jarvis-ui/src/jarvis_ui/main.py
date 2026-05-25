"""Entry point pour jarvis-ui : lance le serveur web FastAPI.

Usage :
    python -m jarvis_ui.main                     # défaut 0.0.0.0:8080
    python -m jarvis_ui.main --port 9090
    python -m jarvis_ui.main --no-chat           # désactive le chat (UI read-only)

Le serveur écoute par défaut sur 0.0.0.0 pour être accessible depuis mobile
LAN. Si le firewall Windows bloque, lancer en admin :
    New-NetFirewallRule -DisplayName "Jarvis UI" -Direction Inbound `
        -LocalPort 8080 -Protocol TCP -Action Allow
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis UI web (FastAPI HUD)")
    parser.add_argument("--host", default="0.0.0.0", help="bind host (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="bind port (default 8080)")
    parser.add_argument(
        "--no-chat",
        action="store_true",
        help="désactive le WebSocket chat (UI read-only sans backend LLM)",
    )
    parser.add_argument(
        "--ollama-model",
        default=None,
        help="modèle Ollama pour le chat (défaut depuis env JARVIS_LLM_MODEL)",
    )
    args = parser.parse_args(argv)

    # Imports lazy : permet à `--help` de marcher même si FastAPI n'est pas installé.
    try:
        import uvicorn  # noqa: PLC0415

        from jarvis_ui.app import create_app  # noqa: PLC0415
    except ImportError as exc:
        print(f"[jarvis-ui] dépendance manquante : {exc}", file=sys.stderr)
        print("[jarvis-ui] installe : pip install -e services/jarvis-ui", file=sys.stderr)
        return 2

    deps = _build_deps(enable_chat=not args.no_chat, ollama_model=args.ollama_model)
    app = create_app(deps)

    print(f"[jarvis-ui] http://{args.host}:{args.port}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _build_deps(*, enable_chat: bool, ollama_model: str | None):
    """Construit les UIDeps en branchant SystemAnswerer + AuditLogger + chat handler."""
    from pathlib import Path  # noqa: PLC0415

    from jarvis_ui.app import UIDeps  # noqa: PLC0415

    # SystemAnswerer pour /api/status
    try:
        from orchestrator.q_and_a import SystemAnswerer  # noqa: PLC0415

        sys_answerer = SystemAnswerer()
    except ImportError:
        sys_answerer = _NullSystemAnswerer()

    # AuditLogger pour /api/audit (réutilise le .local/audit_log.db si dispo)
    audit = None
    try:
        from jarvis_safety.rules.audit import AuditLogger  # noqa: PLC0415

        db_path = Path(".local/audit_log.db")
        if db_path.parent.exists() or db_path.exists():
            audit = AuditLogger(db_path)
    except ImportError:
        pass

    # Chat handler optionnel (None = chat désactivé)
    chat_handler = None
    if enable_chat:
        chat_handler = _build_chat_handler(ollama_model=ollama_model)

    return UIDeps(system_answerer=sys_answerer, audit_logger=audit, chat_handler=chat_handler)


def _build_chat_handler(*, ollama_model: str | None):
    """Branche Ollama → LlmRouter → handler async pour le WebSocket."""
    try:
        from jarvis_llm.clients.ollama_client import (  # noqa: PLC0415
            DEFAULT_LOCAL_MODEL,
            OllamaClient,
        )
    except ImportError:
        return None

    model = ollama_model or DEFAULT_LOCAL_MODEL
    client = OllamaClient(model=model)
    system_prompt = (
        "Tu es Jarvis, un assistant personnel concis et précis. Tu réponds en "
        "français, sans phrases creuses, et tu vas droit au but."
    )

    async def handle(user_msg: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        completion = await client.chat(messages, max_tokens=1024)
        return completion.text

    return handle


class _NullSystemAnswerer:
    """Fallback si orchestrator/q_and_a n'est pas installé."""

    def cpu(self):
        return _NullAnswer()

    def memory(self):
        return _NullAnswer()

    def gpu(self):
        return _NullAnswer()

    def ollama_status(self):
        return _NullAnswer()


class _NullAnswer:
    ok = False
    reason = "orchestrator non installé"

    @property
    def data(self) -> dict:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
