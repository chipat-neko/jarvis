"""Tests de l'app FastAPI : endpoints + WebSocket."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jarvis_safety.rules.audit import AuditEvent, AuditLogger
from jarvis_ui.app import UIDeps, create_app

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeAnswer:
    def __init__(
        self, *, ok: bool, data: dict[str, Any] | None = None, reason: str | None = None
    ) -> None:
        self.ok = ok
        self.data = data or {}
        self.reason = reason


class _FakeSystemAnswerer:
    def __init__(self, *, has_gpu: bool = True) -> None:
        self.has_gpu = has_gpu

    def cpu(self):
        return _FakeAnswer(
            ok=True, data={"percent": 42.0, "count_logical": 16, "count_physical": 8}
        )

    def memory(self):
        return _FakeAnswer(
            ok=True,
            data={"total_gb": 64.0, "used_gb": 22.5, "available_gb": 41.5, "percent": 35.1},
        )

    def gpu(self):
        if not self.has_gpu:
            return _FakeAnswer(ok=False, reason="no gpu")
        return _FakeAnswer(
            ok=True,
            data={
                "gpus": [
                    {
                        "name": "NVIDIA RTX 5070 Ti",
                        "vram_used_mb": 4096,
                        "vram_total_mb": 16384,
                        "utilization_percent": 25,
                        "temp_c": 56,
                    }
                ]
            },
        )

    def ollama_status(self):
        return _FakeAnswer(ok=True, data={"host": "http://x", "status": "running"})


# ---------------------------------------------------------------------------
# Endpoints HTTP
# ---------------------------------------------------------------------------


def test_index_returns_html() -> None:
    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer()))
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "JARVIS" in res.text
    assert "/ws/chat" in res.text


def test_api_status_returns_snapshot() -> None:
    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer()))
    client = TestClient(app)
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["cpu"]["percent"] == 42.0
    assert data["memory"]["total_gb"] == 64.0
    assert data["gpu"]["gpus"][0]["temp_c"] == 56
    assert data["ollama"]["status"] == "running"
    assert "timestamp" in data


def test_api_status_handles_gpu_unavailable() -> None:
    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer(has_gpu=False)))
    client = TestClient(app)
    res = client.get("/api/status")
    data = res.json()
    assert data["gpu"]["available"] is False
    assert "no gpu" in data["gpu"]["reason"]


def test_api_status_extra_services() -> None:
    app = create_app(
        UIDeps(
            system_answerer=_FakeSystemAnswerer(),
            extra_services_status=lambda: {"jarvis-llm": "up", "jarvis-tools": "down"},
        )
    )
    client = TestClient(app)
    data = client.get("/api/status").json()
    assert data["services"] == {"jarvis-llm": "up", "jarvis-tools": "down"}


def test_api_audit_returns_empty_when_no_logger() -> None:
    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer()))
    client = TestClient(app)
    data = client.get("/api/audit").json()
    assert data["available"] is False
    assert data["events"] == []


def test_api_audit_returns_events(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    audit.log(AuditEvent(actor="noah", action="test", payload={"k": "v"}, status="ok"))
    audit.log(AuditEvent(actor="noah", action="other", payload={}, status="refused"))
    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer(), audit_logger=audit))
    client = TestClient(app)
    data = client.get("/api/audit?limit=10").json()
    assert data["available"] is True
    assert len(data["events"]) == 2
    actions = {e["action"] for e in data["events"]}
    assert actions == {"test", "other"}


def test_api_audit_limit_capped() -> None:
    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer()))
    client = TestClient(app)
    # Limit ridiculement haut → ne crashe pas (capé en interne)
    res = client.get("/api/audit?limit=9999999")
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_chat_no_handler_returns_error() -> None:
    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer()))
    client = TestClient(app)
    with client.websocket_connect("/ws/chat") as ws:
        raw = ws.receive_text()
        msg = json.loads(raw)
        assert msg["type"] == "error"
        assert "non configuré" in msg["text"]


@pytest.mark.asyncio
async def test_ws_chat_echo_and_response() -> None:
    async def handler(user: str) -> str:
        return f"reçu: {user}"

    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer(), chat_handler=handler))
    client = TestClient(app)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text("hello")
        echo = json.loads(ws.receive_text())
        reply = json.loads(ws.receive_text())
        assert echo == {"type": "user", "text": "hello"}
        assert reply == {"type": "assistant", "text": "reçu: hello"}


@pytest.mark.asyncio
async def test_ws_chat_accepts_json_payload() -> None:
    async def handler(user: str) -> str:
        return user.upper()

    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer(), chat_handler=handler))
    client = TestClient(app)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"text": "bonjour"}))
        echo = json.loads(ws.receive_text())
        reply = json.loads(ws.receive_text())
        assert echo["text"] == "bonjour"
        assert reply["text"] == "BONJOUR"


@pytest.mark.asyncio
async def test_ws_chat_handler_exception_returns_error() -> None:
    async def boom(user: str) -> str:
        raise RuntimeError("LLM down")

    app = create_app(UIDeps(system_answerer=_FakeSystemAnswerer(), chat_handler=boom))
    client = TestClient(app)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text("test")
        _ = json.loads(ws.receive_text())  # echo
        err = json.loads(ws.receive_text())
        assert err["type"] == "error"
        assert "LLM down" in err["text"]
