"""Générateur de prompts pour tester Jarvis (cf. recherche 105).

Permet de produire un dataset JSONL de N prompts variés couvrant 6 catégories :
code, math, conversation, simple, tools, edge_cases. Chaque prompt vient avec
des `signals` (validateurs automatiques) pour scorer la réponse sans LLM-judge.

Usage :
    python -m scripts.prompt_gen.cli --n 50 --seed 42 --out prompts.jsonl
"""

from scripts.prompt_gen.dataset import Prompt, Signal, load_jsonl, save_jsonl
from scripts.prompt_gen.signals import (
    AstParseSignal,
    JsonParseSignal,
    LengthRangeSignal,
    RegexMatchSignal,
)

__all__ = [
    "AstParseSignal",
    "JsonParseSignal",
    "LengthRangeSignal",
    "Prompt",
    "RegexMatchSignal",
    "Signal",
    "load_jsonl",
    "save_jsonl",
]
