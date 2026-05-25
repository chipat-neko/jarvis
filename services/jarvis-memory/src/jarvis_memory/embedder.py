"""Embedders : convertissent du texte en vecteur (numpy array).

Deux implémentations :
- `HashEmbedder` : déterministe, sans dépendance, basé sur hash. Sert pour
  les tests et comme fallback si `sentence-transformers` n'est pas installé.
- `SentenceTransformerEmbedder` : BGE-large local (lazy import + lazy load
  du modèle au premier `embed()`). ~1.3 GB téléchargés au premier usage,
  cachés ensuite dans `~/.cache/huggingface/`.

Les deux exposent la même API : `.embed(text) -> np.ndarray` (1D, dim fixe).
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Protocol


class Embedder(Protocol):
    """Interface d'un embedder."""

    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Embedder déterministe basé sur SHA-256 (pour tests + fallback).

    Pas un vrai embedder sémantique — deux phrases similaires N'auront PAS de
    vecteurs proches. Mais permet de tester la mécanique de stockage et de
    recherche sans charger 1.3 GB de modèle.
    """

    def __init__(self, *, dim: int = 64) -> None:
        if dim <= 0 or dim > 4096:
            raise ValueError("dim doit être dans [1, 4096]")
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        # Multi-hash pour générer suffisamment de bytes
        raw = b""
        counter = 0
        while len(raw) < self.dim * 4:
            h = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            raw += h
            counter += 1
        floats = []
        for i in range(self.dim):
            chunk = raw[i * 4 : (i + 1) * 4]
            (val,) = struct.unpack("<I", chunk)
            # Normalise [0, 1) puis recentre [-1, 1)
            floats.append((val / 0xFFFFFFFF) * 2 - 1)
        # Normalisation L2 pour avoir une similarité cosinus propre
        norm = math.sqrt(sum(f * f for f in floats)) or 1.0
        return [f / norm for f in floats]


class SentenceTransformerEmbedder:
    """Wrapper lazy autour de `sentence-transformers` (BGE-large par défaut).

    Args:
        model_name: nom du modèle HuggingFace (défaut BAAI/bge-large-en-v1.5).
        device: "cpu" ou "cuda" (None = auto).

    Le modèle est chargé au PREMIER appel `embed()`, pas au constructeur.
    Permet d'importer ce module sans payer le coût ~10s de chargement.
    """

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-large-en-v1.5",
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model = None
        # On découvre dim après chargement
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._ensure_loaded()
        # _ensure_loaded peut throw si pas installé → on n'arrive pas ici
        assert self._dim is not None
        return self._dim

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers pas installé. "
                "Lance : pip install 'jarvis-memory[ml]' ou pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(self.model_name, device=self.device)
        self._dim = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        self._ensure_loaded()
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similarité cosinus entre deux vecteurs (suppose qu'ils sont normalisés)."""
    if len(a) != len(b) or not a:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False))
