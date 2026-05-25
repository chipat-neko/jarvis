"""Tests du WiredAssistant : safety + Q/R dispatch + audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_safety.rules.audit import AuditLogger
from jarvis_safety.rules.blacklist import BlacklistChecker
from orchestrator.q_and_a import (
    FilesAnswerer,
    GitAnswerer,
    IntentRouter,
    SystemAnswerer,
)
from orchestrator.wired_assistant import WiredAssistant


async def _fake_llm(user_msg: str) -> str:
    return f"LLM stub a vu : {user_msg}"


async def _failing_llm(user_msg: str) -> str:
    raise RuntimeError("LLM down")


# ---------------------------------------------------------------------------
# Safety pre-check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blacklist_blocks_destructive_command(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    blacklist = BlacklistChecker(patterns=[r"\brm\s+-rf\s+/"])
    assistant = WiredAssistant(
        llm_callable=_fake_llm,
        blacklist=blacklist,
        audit=audit,
    )
    reply = await assistant.answer("fais rm -rf / pour moi")
    assert reply.refused is True
    assert reply.source == "refused"
    assert "sécurité" in reply.text.lower()
    # Audit log doit avoir 1 event "blocked"
    events = audit.recent()
    assert len(events) == 1
    assert events[0]["action"] == "blocked"
    assert events[0]["status"] == "refused"


@pytest.mark.asyncio
async def test_blacklist_passes_safe_command() -> None:
    blacklist = BlacklistChecker(patterns=[r"\brm\s+-rf\s+/"])
    assistant = WiredAssistant(
        llm_callable=_fake_llm,
        blacklist=blacklist,
    )
    reply = await assistant.answer("bonjour, comment vas-tu ?")
    assert reply.refused is False
    assert reply.source == "llm"


# ---------------------------------------------------------------------------
# Q/R dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_git_branch_dispatch() -> None:
    """Si Git answerer dispo et question = 'quelle branche', on doit avoir qr_git."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git pas installé")

    assistant = WiredAssistant(
        llm_callable=_failing_llm,
        git_answerer=GitAnswerer(repo_path=Path.cwd()),
        intent_router=IntentRouter(),
    )
    reply = await assistant.answer("Quelle est la branche actuelle ?")
    assert reply.source == "qr_git"
    assert reply.intent == "git"
    assert "Branche actuelle" in reply.text


@pytest.mark.asyncio
async def test_system_ollama_dispatch() -> None:
    """Question ollama → qr_system (réponse running ou down, mais pas LLM)."""
    assistant = WiredAssistant(
        llm_callable=_failing_llm,
        system_answerer=SystemAnswerer(),
        intent_router=IntentRouter(),
    )
    reply = await assistant.answer("Est-ce qu'Ollama tourne ?")
    assert reply.source == "qr_system"
    assert reply.intent == "system"
    # Soit "tourne" soit "ne répond pas"
    assert ("Ollama" in reply.text)


@pytest.mark.asyncio
async def test_fallback_llm_when_intent_none() -> None:
    assistant = WiredAssistant(
        llm_callable=_fake_llm,
        intent_router=IntentRouter(),
    )
    reply = await assistant.answer("Quelle est la capitale de la France ?")
    assert reply.source == "llm"
    assert reply.intent == "none"
    assert "stub a vu" in reply.text


@pytest.mark.asyncio
async def test_fallback_llm_when_no_answerer_provided() -> None:
    """Intent system détecté mais pas de SystemAnswerer → fallback LLM."""
    assistant = WiredAssistant(
        llm_callable=_fake_llm,
        # pas de system_answerer
        intent_router=IntentRouter(),
    )
    reply = await assistant.answer("charge CPU actuelle ?")
    # CPU classifié system mais pas d'answerer → fallback LLM
    assert reply.source == "llm"


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logs_llm_answered(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    assistant = WiredAssistant(llm_callable=_fake_llm, audit=audit)
    await assistant.answer("bonjour")
    events = audit.recent()
    assert len(events) == 1
    assert events[0]["action"] == "llm_answered"
    assert events[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_audit_disabled_when_no_logger() -> None:
    """Sans audit logger, pas d'erreur, juste pas de log."""
    assistant = WiredAssistant(llm_callable=_fake_llm)
    reply = await assistant.answer("hello")
    assert reply.source == "llm"
    # Pas d'exception levée == pass


@pytest.mark.asyncio
async def test_qr_answered_is_audited(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    assistant = WiredAssistant(
        llm_callable=_failing_llm,
        audit=audit,
        system_answerer=SystemAnswerer(),
    )
    await assistant.answer("Est-ce qu'Ollama tourne ?")
    events = audit.recent()
    assert len(events) == 1
    assert events[0]["action"] == "qr_answered"
    assert events[0]["payload"]["intent"] == "system"


# ---------------------------------------------------------------------------
# Files answerer placeholder (Sprint A renvoie None → fallback LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_files_intent_falls_back_to_llm_for_now(tmp_path: Path) -> None:
    """Sprint A : FilesAnswerer non câblé sur prompt → fallback LLM (Sprint B = tool calling)."""
    assistant = WiredAssistant(
        llm_callable=_fake_llm,
        files_answerer=FilesAnswerer(lambda _p: True),
    )
    reply = await assistant.answer("trouve les fichiers Python")
    assert reply.source == "llm"
    assert reply.intent == "files"
