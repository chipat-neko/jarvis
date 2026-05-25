"""RAG indexer : indexe des fichiers texte/markdown en chunks avec embeddings.

Workflow :
1. `DocIndexer.scan_directory(root)` itère sur les fichiers texte (.md, .txt, .html…)
2. Chaque fichier est chunké (~512 chars, overlap 80) → un fact par chunk
3. Le fact a `kind="doc_chunk"`, `source=<chemin>`, métadonnées = {path, chunk_idx, total_chunks, mtime}
4. Avant indexation, on supprime les facts déjà indexés pour ce fichier (réindexation propre)

Limites volontaires :
- Pas de détection incrémentale fine (on réindexe tout le fichier dès qu'il change)
- Pas de HTML parsing magique : on indexe le texte brut (on fait un strip de balises minimal)
- Pas de PDF / docx : on reste sur les formats texte plats

Le retrieval se fait via le MemoryReader standard (filtre `kind="doc_chunk"`).
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from jarvis_memory.embedder import Embedder
from jarvis_memory.store import MemoryStore
from jarvis_memory.writer import MemoryWriter

DEFAULT_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt", ".html"})
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 80
DEFAULT_SKIP_DIRS: frozenset[str] = frozenset(
    {".git", "node_modules", ".venv", "__pycache__", "build", "dist", "target", ".pytest_cache"}
)


@dataclass(frozen=True, slots=True)
class IndexResult:
    """Synthèse d'une indexation."""

    files_scanned: int
    chunks_created: int
    files_skipped: int = 0


class DocIndexer:
    """Indexe des fichiers texte sous une racine."""

    def __init__(
        self,
        store: MemoryStore,
        embedder: Embedder,
        *,
        extensions: Iterable[str] = DEFAULT_EXTENSIONS,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        skip_dirs: Iterable[str] = DEFAULT_SKIP_DIRS,
        max_file_size_bytes: int = 2_000_000,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap doit être < chunk_size")
        self.store = store
        self.embedder = embedder
        self.writer = MemoryWriter(store, embedder)
        self.extensions = frozenset(e.lower() for e in extensions)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.skip_dirs = frozenset(skip_dirs)
        self.max_file_size_bytes = max_file_size_bytes

    def scan_directory(self, root: str | Path) -> IndexResult:
        """Scan + indexe tous les fichiers sous `root` (récursif)."""
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            return IndexResult(files_scanned=0, chunks_created=0)

        files_scanned = 0
        chunks_total = 0
        files_skipped = 0
        for path in _walk(root_path, self.extensions, self.skip_dirs):
            try:
                size = path.stat().st_size
            except OSError:
                files_skipped += 1
                continue
            if size > self.max_file_size_bytes:
                files_skipped += 1
                continue
            chunks = self.index_file(path)
            if chunks > 0:
                files_scanned += 1
                chunks_total += chunks
        return IndexResult(
            files_scanned=files_scanned,
            chunks_created=chunks_total,
            files_skipped=files_skipped,
        )

    def index_file(self, path: str | Path) -> int:
        """(Ré)indexe un fichier individuel, retourne le nombre de chunks créés."""
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0
        if path_suffix_lower(p) == ".html":
            text = _strip_html(text)
        text = text.strip()
        if not text:
            return 0
        # Réindexation propre : supprime les anciens chunks pour ce fichier
        self._delete_chunks_for_source(str(p))
        chunks = list(_chunk_text(text, self.chunk_size, self.chunk_overlap))
        for idx, chunk in enumerate(chunks):
            self.writer.add_fact(
                chunk,
                kind="doc_chunk",
                source=str(p),
                metadata={
                    "path": str(p),
                    "chunk_idx": idx,
                    "total_chunks": len(chunks),
                    "ext": path_suffix_lower(p),
                },
                skip_if_duplicate=False,  # on accepte les doublons inter-fichiers
            )
        return len(chunks)

    def _delete_chunks_for_source(self, source: str) -> int:
        """Supprime tous les chunks indexés pour un même `source`."""
        # Pas d'API dédiée dans le store pour rester simple : on cherche par source via brute.
        count = 0
        # MemoryStore.all_with_embeddings filtre par kind mais pas par source — on fait à la main.
        with self.store._lock, self.store._connect() as conn:
            cur = conn.execute("DELETE FROM facts WHERE source = ?", (source,))
            conn.commit()
            count = cur.rowcount
        return count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk(
    root: Path,
    extensions: frozenset[str],
    skip_dirs: frozenset[str],
) -> Iterable[Path]:
    """Itère sur les fichiers du root récursivement en sautant les dossiers blacklistés."""
    for path in root.rglob("*"):
        # Saute les fichiers dans des dossiers blacklistés
        if any(part in skip_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path_suffix_lower(path) not in extensions:
            continue
        yield path


def path_suffix_lower(p: Path) -> str:
    return p.suffix.lower()


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_html(text: str) -> str:
    """Strip HTML très minimaliste : retire scripts/styles puis tous les tags."""
    text = _SCRIPT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _chunk_text(text: str, size: int, overlap: int) -> Iterable[str]:
    """Découpe en chunks de `size` chars avec `overlap` chars de recouvrement."""
    if size <= 0:
        return
    if not text:
        return
    if len(text) <= size:
        yield text
        return
    step = size - overlap
    pos = 0
    while pos < len(text):
        chunk = text[pos : pos + size]
        if not chunk.strip():
            break
        yield chunk
        pos += step
