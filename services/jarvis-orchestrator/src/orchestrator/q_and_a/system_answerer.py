"""Answerer Q/R état système : CPU, RAM, GPU, disque, processus, services.

Utilise `psutil` pour le système et `nvidia-smi` (subprocess) pour le GPU.
Si une dépendance manque, dégrade gracieusement (réponse partielle).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SystemAnswer:
    """Réponse standardisée d'une opération system."""

    ok: bool
    operation: str  # "cpu" | "memory" | "gpu" | "disk" | "processes" | "ollama"
    data: dict = field(default_factory=dict)
    reason: str | None = None


class SystemAnswerer:
    """Helper Q/R état système."""

    def __init__(self, *, nvidia_smi_timeout_sec: float = 3.0) -> None:
        self.nvidia_smi_timeout_sec = nvidia_smi_timeout_sec

    def cpu(self) -> SystemAnswer:
        try:
            import psutil  # noqa: PLC0415 — lazy import
        except ImportError:
            return SystemAnswer(ok=False, operation="cpu", reason="psutil non installé")
        return SystemAnswer(
            ok=True,
            operation="cpu",
            data={
                "percent": psutil.cpu_percent(interval=0.1),
                "count_logical": psutil.cpu_count(),
                "count_physical": psutil.cpu_count(logical=False),
            },
        )

    def memory(self) -> SystemAnswer:
        try:
            import psutil  # noqa: PLC0415
        except ImportError:
            return SystemAnswer(ok=False, operation="memory", reason="psutil non installé")
        vm = psutil.virtual_memory()
        return SystemAnswer(
            ok=True,
            operation="memory",
            data={
                "total_gb": round(vm.total / 1e9, 2),
                "available_gb": round(vm.available / 1e9, 2),
                "used_gb": round(vm.used / 1e9, 2),
                "percent": vm.percent,
            },
        )

    def disk(self, mountpoint: str = "/") -> SystemAnswer:
        try:
            import psutil  # noqa: PLC0415
        except ImportError:
            return SystemAnswer(ok=False, operation="disk", reason="psutil non installé")
        try:
            usage = psutil.disk_usage(mountpoint)
        except OSError as exc:
            return SystemAnswer(ok=False, operation="disk", reason=str(exc))
        return SystemAnswer(
            ok=True,
            operation="disk",
            data={
                "mountpoint": mountpoint,
                "total_gb": round(usage.total / 1e9, 2),
                "free_gb": round(usage.free / 1e9, 2),
                "percent_used": usage.percent,
            },
        )

    def gpu(self) -> SystemAnswer:
        """Parse `nvidia-smi --query-gpu=...` pour récupérer VRAM, util, temp."""
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi is None:
            return SystemAnswer(ok=False, operation="gpu", reason="nvidia-smi introuvable")
        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=self.nvidia_smi_timeout_sec,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return SystemAnswer(ok=False, operation="gpu", reason=str(exc))
        if result.returncode != 0:
            return SystemAnswer(
                ok=False,
                operation="gpu",
                reason=f"nvidia-smi exit {result.returncode}: {result.stderr.strip()}",
            )
        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                gpus.append(
                    {
                        "name": parts[0],
                        "vram_used_mb": _to_int(parts[1]),
                        "vram_total_mb": _to_int(parts[2]),
                        "utilization_percent": _to_int(parts[3]),
                        "temp_c": _to_int(parts[4]),
                    }
                )
        return SystemAnswer(ok=True, operation="gpu", data={"gpus": gpus})

    def processes(self, *, top_n_by_memory: int = 10) -> SystemAnswer:
        try:
            import psutil  # noqa: PLC0415
        except ImportError:
            return SystemAnswer(ok=False, operation="processes", reason="psutil non installé")
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = p.info
                rss_mb = (info.get("memory_info").rss / 1e6) if info.get("memory_info") else 0
                procs.append({"pid": info["pid"], "name": info.get("name", "?"), "rss_mb": round(rss_mb, 1)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x["rss_mb"], reverse=True)
        return SystemAnswer(ok=True, operation="processes", data={"top": procs[:top_n_by_memory]})

    def ollama_status(self, *, host: str = "http://127.0.0.1:11434") -> SystemAnswer:
        """Ping Ollama via http (sans dep réseau lourde, utilise stdlib urllib)."""
        import urllib.error  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        url = f"{host}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return SystemAnswer(ok=True, operation="ollama", data={"host": host, "status": "running"})
                return SystemAnswer(
                    ok=False,
                    operation="ollama",
                    reason=f"HTTP {resp.status}",
                )
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return SystemAnswer(ok=False, operation="ollama", data={"host": host}, reason=str(exc))


def _to_int(s: str) -> int | None:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None
