"""Assistant câblé : ajoute safety (pre-check + audit) + dispatcher Q/R au LlmRouter.

Cette classe orchestre :
1. **Pre-check safety** : si le user_msg matche la blacklist (commande
   destructive), on refuse SANS appeler le LLM, et on logue dans l'audit.
2. **Q/R dispatcher** : si l'intent est `files|git|system`, on tente de
   répondre via les answerers (rapide, déterministe, pas de tokens). Si
   l'answerer échoue ou si l'intent est NONE, on fallback sur le LLM.
3. **Audit log** : chaque requête (succès / refus / fallback) est tracée.

L'idée du Sprint A est de mettre cette colle ENTRE le REPL et le LlmRouter
pour pouvoir activer/désactiver les garde-fous indépendamment et les tester.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from jarvis_safety.rules.audit import AuditEvent, AuditLogger
from jarvis_safety.rules.blacklist import BlacklistChecker
from orchestrator.q_and_a import (
    FilesAnswerer,
    GitAnswerer,
    Intent,
    IntentRouter,
    SystemAnswerer,
)


@dataclass(frozen=True, slots=True)
class AssistantReply:
    """Réponse renvoyée au caller (REPL ou autre)."""

    text: str
    source: str  # "qr_files" | "qr_git" | "qr_system" | "llm" | "refused"
    intent: str  # Intent name or "none"
    refused: bool = False


LlmCallable = Callable[[str], Awaitable[str]]
"""Signature attendue pour appeler le LLM : `async def(user_msg) -> str`."""


class WiredAssistant:
    """Façade qui empile safety + Q/R dispatch + audit autour d'un LLM callable.

    Args:
        llm_callable: fonction async qui prend un user_msg et renvoie une str.
            En général : un wrapper autour de `LlmRouter.chat([messages], intent)`.
        blacklist: checker pour refuser les commandes destructives.
        audit: logger pour tracer chaque requête.
        intent_router: classifier d'intent Q/R.
        files_answerer / git_answerer / system_answerer: les answerers Q/R.
            Si None, le dispatch tombe en fallback LLM pour cette catégorie.
        actor: identifiant utilisé dans l'audit (par défaut "noah").
    """

    def __init__(
        self,
        *,
        llm_callable: LlmCallable,
        blacklist: BlacklistChecker | None = None,
        audit: AuditLogger | None = None,
        intent_router: IntentRouter | None = None,
        files_answerer: FilesAnswerer | None = None,
        git_answerer: GitAnswerer | None = None,
        system_answerer: SystemAnswerer | None = None,
        actor: str = "noah",
    ) -> None:
        self._llm = llm_callable
        self._blacklist = blacklist
        self._audit = audit
        self._intent_router = intent_router or IntentRouter()
        self._files = files_answerer
        self._git = git_answerer
        self._system = system_answerer
        self._actor = actor

    async def answer(self, user_msg: str) -> AssistantReply:
        # 1) Pre-check blacklist
        if self._blacklist is not None:
            match = self._blacklist.check(user_msg)
            if match.matched:
                self._log("blocked", "refused", {"pattern": match.pattern, "msg": user_msg[:200]})
                return AssistantReply(
                    text=(
                        "Je refuse cette commande pour des raisons de sécurité "
                        f"(pattern bloqué : {match.pattern})."
                    ),
                    source="refused",
                    intent="none",
                    refused=True,
                )

        # 2) Q/R dispatcher
        intent_match = self._intent_router.classify(user_msg)
        qr_text: str | None = None
        qr_source: str | None = None

        if intent_match.intent is Intent.FILES and self._files is not None:
            qr_text = _try_files_quick_answer(self._files, user_msg)
            qr_source = "qr_files"
        elif intent_match.intent is Intent.GIT and self._git is not None:
            qr_text = _try_git_quick_answer(self._git, user_msg)
            qr_source = "qr_git"
        elif intent_match.intent is Intent.SYSTEM and self._system is not None:
            qr_text = _try_system_quick_answer(self._system, user_msg)
            qr_source = "qr_system"

        if qr_text is not None and qr_source is not None:
            self._log(
                "qr_answered",
                "ok",
                {"intent": intent_match.intent.value, "msg": user_msg[:200]},
            )
            return AssistantReply(
                text=qr_text,
                source=qr_source,
                intent=intent_match.intent.value,
            )

        # 3) Fallback LLM
        text = await self._llm(user_msg)
        self._log(
            "llm_answered",
            "ok",
            {"intent": intent_match.intent.value, "msg": user_msg[:200]},
        )
        return AssistantReply(
            text=text,
            source="llm",
            intent=intent_match.intent.value,
        )

    def _log(self, action: str, status: str, payload: dict) -> None:
        if self._audit is None:
            return
        # timestamp laissé vide : AuditLogger.log() pose l'ISO 8601 lui-même.
        self._audit.log(
            AuditEvent(
                actor=self._actor,
                action=action,
                payload=payload,
                status=status,
            )
        )


# ---------------------------------------------------------------------------
# Bridges minimaux entre prompt user → answerer (heuristique très simple).
# On reste prudent : si on doute, on retourne None pour fallback LLM.
# ---------------------------------------------------------------------------


def _try_files_quick_answer(answerer: FilesAnswerer, user_msg: str) -> str | None:
    """Pour le Sprint A on ne câble pas de parser fin de prompt. On laisse au LLM
    le soin d'invoquer FilesAnswerer via tool calling (Sprint B). Ici on renvoie
    None pour faire fallback LLM tant qu'on n'a pas un parser robuste.

    Garde la fonction pour que l'API reste stable côté caller.
    """
    _ = answerer, user_msg
    return None


def _try_git_quick_answer(answerer: GitAnswerer, user_msg: str) -> str | None:
    """Réponses très simples : 'branche actuelle' / 'status' / 'derniers commits'."""
    low = user_msg.lower()
    if "branche" in low or "branch" in low:
        res = answerer.current_branch()
        if res.ok and res.text:
            return f"Branche actuelle : {res.text.strip()}"
    if "status" in low:
        res = answerer.status()
        if res.ok:
            if not res.lines:
                return "Le repo est propre (working tree clean)."
            preview = "\n".join(res.lines[:20])
            return f"git status :\n{preview}"
    if "commit" in low or "log" in low:
        res = answerer.log(max_count=5)
        if res.ok:
            return "5 derniers commits :\n" + "\n".join(res.lines)
    return None


def _try_system_quick_answer(answerer: SystemAnswerer, user_msg: str) -> str | None:
    """Réponses ciblées : 'cpu' / 'ram' / 'gpu' / 'ollama'."""
    low = user_msg.lower()
    if "cpu" in low or "processeur" in low:
        res = answerer.cpu()
        if res.ok:
            d = res.data
            return (
                f"CPU : {d['percent']}% utilisé, "
                f"{d['count_physical']} cœurs physiques / {d['count_logical']} logiques."
            )
    if "ram" in low or "mémoire" in low or "memory" in low:
        res = answerer.memory()
        if res.ok:
            d = res.data
            return (
                f"RAM : {d['used_gb']} / {d['total_gb']} Go utilisés ({d['percent']}%), "
                f"{d['available_gb']} Go disponibles."
            )
    if "gpu" in low or "vram" in low or "carte graphique" in low:
        res = answerer.gpu()
        if res.ok and res.data.get("gpus"):
            gpu = res.data["gpus"][0]
            return (
                f"GPU {gpu['name']} : {gpu['vram_used_mb']} / {gpu['vram_total_mb']} Mo VRAM, "
                f"utilisation {gpu['utilization_percent']}%, {gpu['temp_c']}°C."
            )
    if "ollama" in low:
        res = answerer.ollama_status()
        if res.ok:
            return "Ollama tourne et répond correctement."
        return "Ollama ne répond pas (service down ou non démarré)."
    return None
