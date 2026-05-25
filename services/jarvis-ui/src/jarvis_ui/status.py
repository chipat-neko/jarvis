"""Source de vérité pour l'état système exposé par `/api/status`.

Réutilise `SystemAnswerer` côté orchestrator pour CPU/RAM/GPU/Ollama. Le UI
n'invente rien — il agrège ce que SystemAnswerer renvoie déjà.

Pour découpler proprement, on accepte une factory en argument plutôt que
d'instancier SystemAnswerer directement (testable, monkey-patchable).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    """Snapshot complet de l'état système à un instant T."""

    timestamp: float
    cpu: dict
    memory: dict
    gpu: dict
    ollama: dict
    services: dict  # mapping service_name → status

    def to_dict(self) -> dict:
        return asdict(self)


def collect_status(
    *,
    system_answerer,
    extra_services_status: Callable[[], dict] | None = None,
) -> StatusSnapshot:
    """Collecte un snapshot complet de l'état système.

    Args:
        system_answerer: instance de SystemAnswerer (jarvis-orchestrator).
        extra_services_status: callable optionnel renvoyant un dict
            {nom_service: "up"|"down"|"unknown"} pour les services gRPC.
    """
    cpu_res = system_answerer.cpu()
    mem_res = system_answerer.memory()
    gpu_res = system_answerer.gpu()
    ollama_res = system_answerer.ollama_status()

    services = extra_services_status() if extra_services_status else {}

    return StatusSnapshot(
        timestamp=time.time(),
        cpu=cpu_res.data if cpu_res.ok else {"available": False, "reason": cpu_res.reason},
        memory=mem_res.data if mem_res.ok else {"available": False, "reason": mem_res.reason},
        gpu=gpu_res.data if gpu_res.ok else {"available": False, "reason": gpu_res.reason},
        ollama=(
            ollama_res.data if ollama_res.ok else {"available": False, "reason": ollama_res.reason}
        ),
        services=services,
    )
