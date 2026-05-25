"""Tests des embedders + similarité cosinus."""

from __future__ import annotations

import math

import pytest

from jarvis_memory.embedder import HashEmbedder, cosine_similarity


def test_hash_embedder_dim() -> None:
    e = HashEmbedder(dim=128)
    vec = e.embed("hello")
    assert len(vec) == 128


def test_hash_embedder_is_deterministic() -> None:
    e = HashEmbedder()
    assert e.embed("test") == e.embed("test")


def test_hash_embedder_different_texts_different_vecs() -> None:
    e = HashEmbedder()
    a = e.embed("alpha")
    b = e.embed("beta")
    assert a != b


def test_hash_embedder_l2_normalized() -> None:
    e = HashEmbedder(dim=32)
    vec = e.embed("normalize me")
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-5


def test_hash_embedder_invalid_dim() -> None:
    with pytest.raises(ValueError, match="dim"):
        HashEmbedder(dim=0)
    with pytest.raises(ValueError, match="dim"):
        HashEmbedder(dim=10000)


def test_cosine_similarity_identical() -> None:
    a = [1.0, 0.0, 0.0]
    assert cosine_similarity(a, a) == 1.0


def test_cosine_similarity_orthogonal() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_opposite() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_cosine_similarity_different_lengths() -> None:
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_cosine_similarity_empty() -> None:
    assert cosine_similarity([], []) == 0.0


def test_hash_embedder_self_similarity_via_cosine() -> None:
    e = HashEmbedder()
    v = e.embed("anything")
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-5
