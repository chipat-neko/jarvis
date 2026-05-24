"""Tests du classifier d'intent par heuristiques mot-clé."""

from __future__ import annotations

import pytest

from jarvis_llm.intent_classifier import classify
from jarvis_llm.router import IntentClass


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Refactor cette fonction Python", IntentClass.CODE),
        ("J'ai un bug dans mon code Rust", IntentClass.CODE),
        ("```python\nprint(1)\n```", IntentClass.CODE),
        ("Ouvre Spotify et joue de la musique", IntentClass.TOOL_USE),
        ("Recherche sur Google les news", IntentClass.TOOL_USE),
        ("Explique-moi la relativité", IntentClass.COMPLEX),
        ("Compare deux théories scientifiques", IntentClass.COMPLEX),
        ("Quelle heure est-il ?", IntentClass.SIMPLE),
        ("Quel temps fait-il aujourd'hui ?", IntentClass.SIMPLE),
        ("Salut comment ça va", IntentClass.CONVERSATIONAL),
        ("", IntentClass.CONVERSATIONAL),
        ("   ", IntentClass.CONVERSATIONAL),
    ],
)
def test_classify(text: str, expected: IntentClass) -> None:
    assert classify(text) is expected
