"""Answerer Q/R sur git : status, log, branches, dernier commit.

Utilise `git` en sous-process (pas de gitpython pour éviter une dep). Le repo
est passé au constructeur, ou auto-détecté en partant du cwd.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GitAnswer:
    """Réponse standardisée d'une opération git."""

    ok: bool
    operation: str  # "status" | "log" | "branches" | "last_commit"
    lines: list[str] = field(default_factory=list)
    text: str | None = None
    reason: str | None = None


class GitAnswerer:
    """Wrapper minimal sur le binaire `git` (CLI).

    Args:
        repo_path: chemin du repo. Si None, utilise cwd.
        timeout_sec: timeout par appel git.
    """

    def __init__(self, repo_path: str | Path | None = None, *, timeout_sec: float = 5.0) -> None:
        self.repo_path = Path(repo_path) if repo_path is not None else Path.cwd()
        self.timeout_sec = timeout_sec
        self._git_bin = shutil.which("git")

    def _run(self, args: list[str]) -> GitAnswer:
        if self._git_bin is None:
            return GitAnswer(
                ok=False, operation=args[0] if args else "?", reason="git introuvable dans PATH"
            )
        try:
            result = subprocess.run(
                [self._git_bin, "-C", str(self.repo_path), *args],
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return GitAnswer(ok=False, operation=args[0], reason=f"timeout {self.timeout_sec}s")
        if result.returncode != 0:
            return GitAnswer(
                ok=False,
                operation=args[0],
                reason=f"git exit {result.returncode}: {result.stderr.strip()}",
            )
        text = result.stdout
        lines = [ln for ln in text.splitlines() if ln]
        return GitAnswer(ok=True, operation=args[0], lines=lines, text=text)

    def status(self) -> GitAnswer:
        """Liste les fichiers modifiés / staged / untracked (format porcelain)."""
        return self._run(["status", "--porcelain"])

    def log(self, *, max_count: int = 10, since: str | None = None) -> GitAnswer:
        """N derniers commits, format `<sha>|<auteur>|<date>|<message>`."""
        args = [
            "log",
            f"-n{max_count}",
            "--pretty=format:%h|%an|%ad|%s",
            "--date=short",
        ]
        if since:
            args.append(f"--since={since}")
        return self._run(args)

    def branches(self) -> GitAnswer:
        """Liste les branches locales (sans détail remote)."""
        return self._run(["branch", "--list"])

    def last_commit(self) -> GitAnswer:
        """Dernier commit en détail : sha, auteur, date, message."""
        return self._run(["log", "-1", "--pretty=format:%H%n%an%n%ad%n%s", "--date=iso"])

    def current_branch(self) -> GitAnswer:
        """Nom de la branche actuellement checkout."""
        return self._run(["rev-parse", "--abbrev-ref", "HEAD"])
