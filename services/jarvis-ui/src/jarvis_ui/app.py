"""Application FastAPI : web HUD de Jarvis.

Layout 3 colonnes (cf recherche 104) :
- gauche : état système temps réel (CPU/RAM/GPU/Ollama/services)
- centre : chat multi-tour via WebSocket
- droite : audit log + (futur) projets

Endpoints :
- `GET /` → HTML inline (HUD)
- `GET /api/status` → snapshot état système (polling 2s côté client)
- `GET /api/audit?limit=N` → derniers events audit
- `WS /ws/chat` → conversation streaming texte ({user|assistant|tool|error})

Le service écoute `0.0.0.0:8080` par défaut pour être accessible depuis mobile
LAN (penser à ouvrir le firewall Windows : `New-NetFirewallRule -DisplayName
"Jarvis UI" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow`).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from jarvis_ui.html import HUD_HTML
from jarvis_ui.status import collect_status

ChatHandler = Callable[[str], Awaitable[str]]
"""Signature attendue : async fn(user_msg) -> assistant_text.

Le caller (orchestrator) branche ici son WiredAssistant ou tool-loop.
"""


@dataclass(frozen=True, slots=True)
class UIDeps:
    """Dépendances injectées pour découpler du reste du code."""

    system_answerer: object  # SystemAnswerer protocol
    audit_logger: object | None = None  # AuditLogger | None
    chat_handler: ChatHandler | None = None
    extra_services_status: Callable[[], dict] | None = None


def create_app(deps: UIDeps) -> FastAPI:
    """Construit l'app FastAPI configurée avec les dépendances.

    On accepte les dépendances par injection plutôt qu'en globals → testable.
    """
    app = FastAPI(title="Jarvis HUD", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return HUD_HTML

    @app.get("/api/status")
    def status() -> JSONResponse:
        snap = collect_status(
            system_answerer=deps.system_answerer,
            extra_services_status=deps.extra_services_status,
        )
        return JSONResponse(snap.to_dict())

    @app.get("/api/audit")
    def audit(limit: int = 50) -> JSONResponse:
        if deps.audit_logger is None:
            return JSONResponse({"events": [], "available": False})
        events = deps.audit_logger.recent(limit=min(max(1, limit), 500))
        return JSONResponse({"events": events, "available": True})

    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket) -> None:
        await ws.accept()
        if deps.chat_handler is None:
            await ws.send_text(json.dumps({"type": "error", "text": "chat_handler non configuré"}))
            await ws.close()
            return
        try:
            while True:
                raw = await ws.receive_text()
                user_msg = _parse_user_message(raw)
                if user_msg is None:
                    await ws.send_text(json.dumps({"type": "error", "text": "message invalide"}))
                    continue
                # Echo de la question (utile pour l'historique côté UI)
                await ws.send_text(json.dumps({"type": "user", "text": user_msg}))
                try:
                    answer = await deps.chat_handler(user_msg)
                except Exception as exc:
                    await ws.send_text(
                        json.dumps({"type": "error", "text": f"{type(exc).__name__}: {exc}"})
                    )
                    continue
                await ws.send_text(json.dumps({"type": "assistant", "text": answer}))
        except WebSocketDisconnect:
            return

    return app


def _parse_user_message(raw: str) -> str | None:
    """Accepte soit du texte brut, soit un JSON {"text": "..."}."""
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            value = data.get("text") or data.get("message")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    return raw
