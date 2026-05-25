"""Whitelist des chemins d'écriture autorisés.

Jarvis n'écrit que dans les dossiers explicitement listés (cf rules.yaml).
Tentative d'écriture en dehors → refus. Path traversal (`..`) résolu avant check.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PathCheck:
    allowed: bool
    resolved_path: str
    reason: str | None


class PathWhitelist:
    """Vérifie qu'un chemin candidat à l'écriture est dans la whitelist.

    Les chemins de la whitelist peuvent contenir `~` (expansion home) et des
    variables d'environnement. La résolution se fait au moment de la
    construction (donc les chemins relatifs sont relatifs au cwd actuel).
    """

    def __init__(self, allowed_paths: list[str]) -> None:
        self._allowed_resolved = [self._resolve(p) for p in allowed_paths]

    @staticmethod
    def _resolve(path: str) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(path))
        return Path(expanded).resolve()

    def check(self, target: str | Path) -> PathCheck:
        """Retourne PathCheck(allowed, resolved_path, reason)."""
        try:
            resolved = self._resolve(str(target))
        except (OSError, RuntimeError) as exc:
            return PathCheck(
                allowed=False,
                resolved_path=str(target),
                reason=f"chemin invalide : {exc}",
            )

        if not self._allowed_resolved:
            return PathCheck(
                allowed=False,
                resolved_path=str(resolved),
                reason="whitelist vide (aucun chemin autorisé en écriture)",
            )

        for allowed in self._allowed_resolved:
            try:
                resolved.relative_to(allowed)
                return PathCheck(allowed=True, resolved_path=str(resolved), reason=None)
            except ValueError:
                continue

        return PathCheck(
            allowed=False,
            resolved_path=str(resolved),
            reason=(
                f"chemin {resolved} en dehors de la whitelist "
                f"({', '.join(str(p) for p in self._allowed_resolved)})"
            ),
        )

    def is_allowed(self, target: str | Path) -> bool:
        return self.check(target).allowed
