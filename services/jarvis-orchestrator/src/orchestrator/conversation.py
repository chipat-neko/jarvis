"""Historique conversationnel persistant pour le REPL Jarvis.

Garde une fenêtre glissante des N derniers tours (user + assistant) en mémoire
et sur disque pour permettre de reprendre une conversation après redémarrage.

Format de stockage : JSON unique, lisible à la main si besoin.
Path par défaut : `<repo>/.local/conversation.json` (gitignored).

Pour le MVP, on garde tout en JSON simple. Plus tard (sprint Memory S5+), on
basculera sur Mem0 + sqlite-vec pour la mémoire long-terme intelligente.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Role = Literal["user", "assistant", "system"]

# Fenêtre par défaut : 20 messages = ~10 tours user/assistant en mémoire.
# Le system prompt est compté à part, il est toujours en tête.
DEFAULT_HISTORY_WINDOW = 20


def _default_persistence_path() -> Path:
    """Path par défaut pour stocker l'historique conversation.

    On vise `<repo>/.local/conversation.json` quand on tourne depuis le repo,
    fallback `~/.jarvis/conversation.json` sinon.
    """
    cwd = Path.cwd()
    # Si on est dans le repo (présence du Cargo.toml workspace + pyproject racine)
    if (cwd / "Cargo.toml").exists() and (cwd / "pyproject.toml").exists():
        return cwd / ".local" / "conversation.json"
    return Path.home() / ".jarvis" / "conversation.json"


@dataclass(frozen=True, slots=True)
class Message:
    """Un message dans l'historique."""

    role: Role
    content: str
    timestamp: str  # ISO 8601 UTC

    @classmethod
    def now(cls, role: Role, content: str) -> Message:
        return cls(role=role, content=content, timestamp=datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content, "ts": self.timestamp}

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("ts", datetime.now(UTC).isoformat()),
        )


@dataclass
class Conversation:
    """Historique conversationnel : sliding window + persistance JSON.

    Args:
        system_prompt: instruction système (toujours en tête, jamais évincée).
        window: nombre max de messages user/assistant gardés (défaut 20).
        path: fichier de persistance. None = pas de persistance (mode mémoire seule).
    """

    system_prompt: str
    window: int = DEFAULT_HISTORY_WINDOW
    path: Path | None = field(default_factory=_default_persistence_path)
    _messages: list[Message] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.path is not None:
            self.load()

    def add_user(self, content: str) -> None:
        self._append(Message.now("user", content))

    def add_assistant(self, content: str) -> None:
        self._append(Message.now("assistant", content))

    def _append(self, msg: Message) -> None:
        self._messages.append(msg)
        # Sliding window : garde seulement les `window` derniers messages.
        if len(self._messages) > self.window:
            self._messages = self._messages[-self.window :]
        self._save_if_needed()

    def reset(self) -> None:
        """Efface l'historique en mémoire et sur disque."""
        self._messages = []
        if self.path is not None and self.path.exists():
            self.path.unlink()

    def as_messages(self) -> list[dict[str, str]]:
        """Retourne la liste au format Ollama/OpenAI (system + historique).

        Le system prompt est toujours en tête, suivi de la fenêtre glissante des
        messages user/assistant.
        """
        result: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        for m in self._messages:
            result.append({"role": m.role, "content": m.content})
        return result

    def messages(self) -> list[Message]:
        """Retourne la liste des messages user/assistant (sans le system prompt)."""
        return list(self._messages)

    def turn_count(self) -> int:
        """Nombre de tours utilisateur dans l'historique."""
        return sum(1 for m in self._messages if m.role == "user")

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Charge l'historique depuis `self.path` si le fichier existe."""
        if self.path is None or not self.path.exists():
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._messages = [Message.from_dict(m) for m in data.get("messages", [])]
        except (OSError, json.JSONDecodeError, KeyError):
            # Fichier corrompu ou illisible : on repart à vide plutôt que de planter.
            self._messages = []

    def _save_if_needed(self) -> None:
        if self.path is None:
            return
        self.save()

    def save(self) -> None:
        """Écrit l'historique sur disque (atomique : tmp + rename)."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "saved_at": datetime.now(UTC).isoformat(),
            "messages": [m.to_dict() for m in self._messages],
        }
        # Écriture atomique : on évite que la conversation soit corrompue
        # si le process crash en plein write.
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix="conv-", suffix=".json", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            # Nettoyage du tmp si problème, puis re-raise pour visibilité.
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
