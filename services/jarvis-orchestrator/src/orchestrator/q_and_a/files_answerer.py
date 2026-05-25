"""Answerer Q/R sur fichiers locaux (avec whitelist obligatoire).

Méthodes :
- `find(glob_pattern, *, root)` : trouve les fichiers qui matchent un pattern (glob)
- `grep(text, *, root, pattern_glob)` : grep récursif d'un texte dans les fichiers
- `read(path)` : lit un fichier si dans la whitelist

Toutes les opérations sont read-only et respectent la PathWhitelist passée
au constructeur (ne lit que dans des chemins autorisés explicitement).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileMatch:
    """Un fichier ou une ligne qui matche une recherche."""

    path: str
    line_number: int | None = None
    line_content: str | None = None
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class FilesAnswer:
    """Réponse standardisée d'une opération files."""

    ok: bool
    operation: str  # "find" | "grep" | "read"
    matches: list[FileMatch] = field(default_factory=list)
    text: str | None = None  # pour read
    reason: str | None = None  # si !ok


class FilesAnswerer:
    """Helper Q/R fichiers.

    Args:
        whitelist_check: fonction (path: str | Path) -> bool. Si False, refus.
            Typiquement `jarvis_safety.rules.paths.PathWhitelist.is_allowed`.
        max_grep_matches: limite haute pour éviter spam.
        max_file_size_bytes: taille max d'un fichier qu'on accepte de lire.
    """

    def __init__(
        self,
        whitelist_check,
        *,
        max_grep_matches: int = 100,
        max_file_size_bytes: int = 2_000_000,
    ) -> None:
        self.whitelist_check = whitelist_check
        self.max_grep_matches = max_grep_matches
        self.max_file_size_bytes = max_file_size_bytes

    def find(self, glob_pattern: str, *, root: str | Path) -> FilesAnswer:
        """Trouve les fichiers matchant `glob_pattern` sous `root`."""
        root_path = Path(root)
        if not self.whitelist_check(root_path):
            return FilesAnswer(
                ok=False,
                operation="find",
                reason=f"root '{root_path}' hors whitelist",
            )
        if not root_path.exists() or not root_path.is_dir():
            return FilesAnswer(
                ok=False,
                operation="find",
                reason=f"root '{root_path}' n'existe pas ou n'est pas un dossier",
            )

        matches: list[FileMatch] = []
        try:
            for p in root_path.rglob(glob_pattern):
                if p.is_file():
                    try:
                        size = p.stat().st_size
                    except OSError:
                        size = None
                    matches.append(FileMatch(path=str(p), size_bytes=size))
                    if len(matches) >= self.max_grep_matches:
                        break
        except OSError as exc:
            return FilesAnswer(ok=False, operation="find", reason=f"erreur OS: {exc}")

        return FilesAnswer(ok=True, operation="find", matches=matches)

    def grep(
        self,
        text: str,
        *,
        root: str | Path,
        pattern_glob: str = "**/*",
    ) -> FilesAnswer:
        """Grep simple : cherche `text` (string) dans tous les fichiers matchant `pattern_glob`."""
        root_path = Path(root)
        if not self.whitelist_check(root_path):
            return FilesAnswer(
                ok=False,
                operation="grep",
                reason=f"root '{root_path}' hors whitelist",
            )
        if not text:
            return FilesAnswer(ok=False, operation="grep", reason="texte de recherche vide")

        matches: list[FileMatch] = []
        for p in root_path.rglob(pattern_glob):
            if not p.is_file():
                continue
            try:
                if p.stat().st_size > self.max_file_size_bytes:
                    continue
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, start=1):
                        if text in line:
                            matches.append(
                                FileMatch(
                                    path=str(p),
                                    line_number=i,
                                    line_content=line.rstrip("\n"),
                                )
                            )
                            if len(matches) >= self.max_grep_matches:
                                return FilesAnswer(
                                    ok=True, operation="grep", matches=matches
                                )
            except OSError:
                continue
        return FilesAnswer(ok=True, operation="grep", matches=matches)

    def read(self, path: str | Path) -> FilesAnswer:
        """Lit un fichier texte (max max_file_size_bytes) si dans la whitelist."""
        p = Path(path)
        if not self.whitelist_check(p):
            return FilesAnswer(
                ok=False,
                operation="read",
                reason=f"chemin '{p}' hors whitelist",
            )
        if not p.exists():
            return FilesAnswer(ok=False, operation="read", reason=f"fichier '{p}' inexistant")
        if not p.is_file():
            return FilesAnswer(ok=False, operation="read", reason=f"'{p}' n'est pas un fichier")
        try:
            size = p.stat().st_size
        except OSError as exc:
            return FilesAnswer(ok=False, operation="read", reason=f"stat échoué: {exc}")
        if size > self.max_file_size_bytes:
            return FilesAnswer(
                ok=False,
                operation="read",
                reason=f"fichier trop gros ({size} > {self.max_file_size_bytes})",
            )
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FilesAnswer(ok=False, operation="read", reason=f"read échoué: {exc}")
        return FilesAnswer(ok=True, operation="read", text=text)
