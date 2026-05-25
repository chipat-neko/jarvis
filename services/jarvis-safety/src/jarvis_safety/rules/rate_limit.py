"""Rate limiting des actions Jarvis.

Token bucket simple : chaque catégorie d'action (pc_action, email, slack, …)
a un quota par fenêtre temporelle (60s, 3600s…). Au-delà, refus + audit.
Stocké en mémoire (reset au redémarrage du service) — pour persistance, on
peut basculer en SQLite plus tard.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class RateLimitCheck:
    allowed: bool
    count_in_window: int
    limit: int
    window_sec: int
    reason: str | None


class RateLimiter:
    """Stockage par catégorie : deque des timestamps des N dernières actions.

    À chaque check, on évince les timestamps en dehors de la fenêtre puis
    on compare avec la limite. O(N) par appel mais N est borné par la limite.
    """

    def __init__(self, limits: dict[str, tuple[int, int]]) -> None:
        """limits = {category: (max_count, window_sec)} ex {"pc_action": (30, 60)}"""
        self.limits = limits
        self._lock = Lock()
        self._timestamps: dict[str, deque[float]] = {cat: deque() for cat in limits}

    def check_and_consume(self, category: str) -> RateLimitCheck:
        """Si autorisé, consomme un token et retourne allowed=True.

        Si refusé, ne consomme rien.
        """
        if category not in self.limits:
            # Catégorie inconnue : par défaut on autorise mais log
            return RateLimitCheck(
                allowed=True,
                count_in_window=0,
                limit=0,
                window_sec=0,
                reason=f"catégorie '{category}' non configurée (pass-through)",
            )

        limit, window = self.limits[category]
        now = time.monotonic()
        cutoff = now - window

        with self._lock:
            dq = self._timestamps[category]
            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= limit:
                return RateLimitCheck(
                    allowed=False,
                    count_in_window=len(dq),
                    limit=limit,
                    window_sec=window,
                    reason=(
                        f"rate limit dépassé pour '{category}' ({len(dq)}/{limit} en {window}s)"
                    ),
                )

            dq.append(now)
            return RateLimitCheck(
                allowed=True,
                count_in_window=len(dq),
                limit=limit,
                window_sec=window,
                reason=None,
            )

    def current_count(self, category: str) -> int:
        """Nombre d'actions actuellement dans la fenêtre pour cette catégorie."""
        if category not in self.limits:
            return 0
        _, window = self.limits[category]
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            dq = self._timestamps[category]
            return sum(1 for t in dq if t >= cutoff)
