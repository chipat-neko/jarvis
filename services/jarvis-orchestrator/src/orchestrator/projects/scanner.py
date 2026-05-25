"""Scanner de projets : inspecte `d:/assistant_ai/*/` et synthétise leur état.

Pour chaque sous-dossier :
- détecte si c'est un repo git → branche actuelle + nombre de fichiers modifiés
- récupère la dernière activité (mtime le plus récent dans le dossier, top niveau)
- estime la taille (somme rapide des fichiers top-niveau, pas récursif)

Pas de coût réseau, pas de LLM — c'est un read-only scan local.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    """Snapshot d'un projet à un instant T."""

    name: str
    path: str
    is_git_repo: bool
    current_branch: str | None = None
    dirty_files: int = 0
    last_activity: str | None = None  # ISO 8601
    size_bytes_estimate: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "is_git_repo": self.is_git_repo,
            "current_branch": self.current_branch,
            "dirty_files": self.dirty_files,
            "last_activity": self.last_activity,
            "size_bytes_estimate": self.size_bytes_estimate,
            "notes": list(self.notes),
        }


class ProjectScanner:
    """Scanne un dossier-parent et retourne un ProjectInfo par sous-dossier.

    Args:
        root: dossier-parent à scanner (ex `d:/assistant_ai`).
        git_timeout_sec: timeout par appel git (par défaut 3s).
        skip_hidden: skip les dossiers commençant par `.` (ex `.venv`, `.git`).
    """

    def __init__(
        self,
        root: str | Path,
        *,
        git_timeout_sec: float = 3.0,
        skip_hidden: bool = True,
    ) -> None:
        self.root = Path(root)
        self.git_timeout_sec = git_timeout_sec
        self.skip_hidden = skip_hidden
        self._git_bin = shutil.which("git")

    def scan(self) -> list[ProjectInfo]:
        if not self.root.exists() or not self.root.is_dir():
            return []
        out: list[ProjectInfo] = []
        for entry in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue
            if self.skip_hidden and entry.name.startswith("."):
                continue
            out.append(self._inspect(entry))
        return out

    def _inspect(self, path: Path) -> ProjectInfo:
        is_git = (path / ".git").exists()
        branch: str | None = None
        dirty = 0
        notes: list[str] = []
        if is_git and self._git_bin:
            branch = self._git_branch(path) or None
            dirty = self._git_dirty_count(path)
        elif is_git and not self._git_bin:
            notes.append("git binaire absent du PATH — état git indisponible")

        last_activity = self._latest_mtime(path)
        size = self._top_level_size(path)
        return ProjectInfo(
            name=path.name,
            path=str(path),
            is_git_repo=is_git,
            current_branch=branch,
            dirty_files=dirty,
            last_activity=last_activity,
            size_bytes_estimate=size,
            notes=tuple(notes),
        )

    def _git_branch(self, path: Path) -> str | None:
        try:
            result = subprocess.run(
                [self._git_bin, "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=self.git_timeout_sec,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _git_dirty_count(self, path: Path) -> int:
        try:
            result = subprocess.run(
                [self._git_bin, "-C", str(path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=self.git_timeout_sec,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 0
        if result.returncode != 0:
            return 0
        return sum(1 for line in result.stdout.splitlines() if line.strip())

    def _latest_mtime(self, path: Path) -> str | None:
        """Mtime maximum sur les fichiers top-niveau + sur le dossier lui-même.

        Volontairement non-récursif : un repo de 100k fichiers ferait timeout. Si
        l'IDE / git met à jour des fichiers top-niveau, on capte. Sinon le mtime
        du dossier `.git` suffit en général.
        """
        try:
            mtimes = [path.stat().st_mtime]
        except OSError:
            return None
        try:
            for child in path.iterdir():
                try:
                    mtimes.append(child.stat().st_mtime)
                except OSError:
                    continue
        except OSError:
            pass
        latest = max(mtimes)
        return datetime.fromtimestamp(latest, tz=UTC).isoformat()

    def _top_level_size(self, path: Path) -> int:
        total = 0
        try:
            for child in path.iterdir():
                try:
                    if child.is_file():
                        total += child.stat().st_size
                except OSError:
                    continue
        except OSError:
            return 0
        return total
