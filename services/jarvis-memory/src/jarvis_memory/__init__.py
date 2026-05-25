"""jarvis-memory : mémoire long-terme cross-session.

Layers :
- `embedder` : text → vecteur (HashEmbedder pour tests, SentenceTransformer
  pour la prod, lazy import).
- `store` : SQLite append-only, embeddings packés en BLOB, pas de sqlite-vec
  pour rester sans deps lourdes (brute-force cosine en Python < 50ms pour 10k facts).
- `writer` : heuristique d'extraction de faits + persistance + dedup.
- `reader` : retrieval top-k par similarité cosinus.
- `rag` (Phase 3) : indexer de docs (chunking + write par chunk).

Usage type côté Conversation :
    embedder = HashEmbedder()              # ou SentenceTransformerEmbedder() pour la prod
    store = MemoryStore(".local/memory.db")
    writer = MemoryWriter(store, embedder)
    reader = MemoryReader(store, embedder)

    # À la fin d'une session
    writer.extract_from_text(last_user_message)

    # Au démarrage de la session suivante
    relevant = reader.search("nouveau prompt user", top_k=3)
"""

from jarvis_memory.embedder import (
    Embedder,
    HashEmbedder,
    SentenceTransformerEmbedder,
    cosine_similarity,
)
from jarvis_memory.rag import DocIndexer, IndexResult
from jarvis_memory.reader import MemoryReader, Recall
from jarvis_memory.store import Fact, MemoryStore
from jarvis_memory.writer import MemoryWriter, WriteResult

__all__ = [
    "DocIndexer",
    "Embedder",
    "Fact",
    "HashEmbedder",
    "IndexResult",
    "MemoryReader",
    "MemoryStore",
    "MemoryWriter",
    "Recall",
    "SentenceTransformerEmbedder",
    "WriteResult",
    "cosine_similarity",
]
