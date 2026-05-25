"""Modèle Prompt + I/O JSONL + sampling stratifié déterministe."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Signal:
    """Un validateur sur la réponse du modèle.

    Attributes:
        kind: "regex" | "ast" | "json" | "length_range"
        params: paramètres spécifiques (pattern, lang, min/max, etc.)
        required: si False, le signal compte comme bonus
    """

    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    required: bool = True


@dataclass(frozen=True, slots=True)
class Prompt:
    """Un cas de test prompt + métadonnées + signaux de validation.

    Attributes:
        id: identifiant unique (déterministe : `{category}_{idx:04d}`)
        category: "code" | "math" | "conversation" | "simple" | "tools" | "edge"
        difficulty: "L1" (facile) … "L5" (hardcore)
        text: le prompt envoyé au modèle
        expected: réponse attendue (peut être partielle, utilisée par signals)
        signals: liste des validateurs à appliquer
        metadata: tags libres (lang, topic…)
    """

    id: str
    category: str
    difficulty: str
    text: str
    expected: str | None = None
    signals: tuple[Signal, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signals"] = [asdict(s) for s in self.signals]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Prompt:
        signals = tuple(Signal(**s) for s in d.get("signals", []))
        return cls(
            id=d["id"],
            category=d["category"],
            difficulty=d["difficulty"],
            text=d["text"],
            expected=d.get("expected"),
            signals=signals,
            metadata=d.get("metadata", {}),
        )


def save_jsonl(prompts: list[Prompt], path: str | Path) -> None:
    """Sauvegarde une liste de prompts en JSONL (one prompt per line)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for prompt in prompts:
            f.write(json.dumps(prompt.to_dict(), ensure_ascii=False))
            f.write("\n")


def load_jsonl(path: str | Path) -> list[Prompt]:
    """Charge un fichier JSONL en liste de Prompt."""
    p = Path(path)
    prompts: list[Prompt] = []
    with p.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            prompts.append(Prompt.from_dict(json.loads(line)))
    return prompts


def stratified_sample(
    prompts: list[Prompt],
    n: int,
    *,
    seed: int = 42,
) -> list[Prompt]:
    """Sample stratifié par catégorie : essaie de garder une répartition équilibrée.

    Si n > len(prompts), retourne tout. Sinon, on prend ~n/cat par catégorie,
    puis on complète aléatoirement pour atteindre exactement n.
    """
    if n >= len(prompts):
        return list(prompts)

    rng = random.Random(seed)
    by_cat: dict[str, list[Prompt]] = defaultdict(list)
    for p in prompts:
        by_cat[p.category].append(p)

    n_cats = len(by_cat)
    per_cat = max(1, n // n_cats)

    sample: list[Prompt] = []
    for cat in sorted(by_cat):
        items = by_cat[cat][:]
        rng.shuffle(items)
        sample.extend(items[:per_cat])

    # Compléter si on n'a pas assez (catégories sous-peuplées)
    rest = [p for p in prompts if p not in sample]
    rng.shuffle(rest)
    while len(sample) < n and rest:
        sample.append(rest.pop())

    # Tronquer si on en a trop (pour respecter exactement n)
    return sample[:n]
