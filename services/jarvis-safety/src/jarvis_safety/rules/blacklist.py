"""Blacklist de commandes — refus avant exécution.

Une commande qui matche un des patterns regex est refusée. Le test est
case-insensitive et normalise les espaces. Pas de bypass possible côté code
(les règles côté LLM ne sont qu'un complément).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlacklistMatch:
    matched: bool
    pattern: str | None
    reason: str | None


class BlacklistChecker:
    """Vérifie qu'une commande ne matche aucun pattern interdit.

    Compile les patterns une fois au constructeur pour éviter de re-compiler
    à chaque check.
    """

    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns
        self._compiled = [(re.compile(p, re.IGNORECASE), p) for p in patterns]

    def check(self, command: str) -> BlacklistMatch:
        """Retourne (matched=True, pattern, reason) si la commande est interdite."""
        normalized = " ".join(command.split())
        for regex, raw in self._compiled:
            if regex.search(normalized):
                return BlacklistMatch(
                    matched=True,
                    pattern=raw,
                    reason=f"commande refusée (match pattern blacklist: {raw!r})",
                )
        return BlacklistMatch(matched=False, pattern=None, reason=None)

    def is_allowed(self, command: str) -> bool:
        return not self.check(command).matched
