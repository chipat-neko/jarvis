"""Redaction des secrets avant log / display.

Tout texte qui passe par `redact()` voit ses API keys, tokens, clés privées,
remplacés par `[REDACTED]`. Utilisé avant l'écriture audit log et avant
l'affichage à l'utilisateur si nécessaire.
"""

from __future__ import annotations

import re

REDACTED_MARKER = "[REDACTED]"


class Redactor:
    """Compile les patterns regex à la construction, redact à la demande."""

    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns
        self._compiled = [re.compile(p) for p in patterns]

    def redact(self, text: str) -> str:
        """Remplace toutes les occurrences de chaque pattern par [REDACTED]."""
        if not text:
            return text
        out = text
        for regex in self._compiled:
            out = regex.sub(REDACTED_MARKER, out)
        return out

    def redact_dict(self, data: dict) -> dict:
        """Redact récursive sur les valeurs string d'un dict (pour les payloads audit)."""
        return {k: self._redact_value(v) for k, v in data.items()}

    def _redact_value(self, v):
        if isinstance(v, str):
            return self.redact(v)
        if isinstance(v, dict):
            return self.redact_dict(v)
        if isinstance(v, list):
            return [self._redact_value(x) for x in v]
        return v
