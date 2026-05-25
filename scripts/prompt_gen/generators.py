"""Générateurs : instancient les templates avec des variables pour produire des prompts.

Chaque générateur prend un RNG seedé et un nombre cible et retourne une liste
de Prompts. Les variables sont tirées de pools fixes (déterministes par seed).
"""

from __future__ import annotations

import random
from typing import Any

from scripts.prompt_gen.dataset import Prompt, Signal
from scripts.prompt_gen.templates import (
    CODE_TEMPLATES,
    CONVERSATION_TEMPLATES,
    EDGE_TEMPLATES,
    MATH_TEMPLATES,
    SIMPLE_TEMPLATES,
    TOOLS_TEMPLATES,
    Template,
)

# ---------------------------------------------------------------------------
# Pools de variables (statiques, déterministes)
# ---------------------------------------------------------------------------

_CODE_VARS = {
    "target": ["la somme", "le max", "le min", "la moyenne", "le produit", "le tri croissant"],
    "fn_name": ["compute", "process_items", "normalize_input", "validate_payload"],
    "behavior": [
        "filtre les valeurs négatives",
        "transforme une chaîne en slug",
        "valide un email avec regex",
        "compte les occurrences",
    ],
    "class_name": ["TaskQueue", "RateLimiter", "ResultCache", "EventBuffer"],
    "snippet": [
        "def f(x):\n    return x + 1",
        "x = 1\ny = x * 2\nprint(y)",
        "class A:\n    pass",
    ],
}

_MATH_VARS = {
    "a": [7, 12, 23, 41, 99, 128, 1024],
    "b": [3, 8, 17, 29, 50, 77, 200],
    "value": [5, 10, 100, 250, 500],
    "unit_from": ["km", "m", "kg", "L", "°C"],
    "unit_to": ["miles", "cm", "lb", "gal", "°F"],
    "nth": ["10ème", "15ème", "20ème", "25ème"],
}

_CONV_VARS = {
    "action_verb": ["vas-tu", "te sens-tu", "te portes-tu"],
    "n_sentences": ["2", "3", "5"],
    "concept": [
        "un microservice",
        "un microcontrôleur",
        "le tool calling LLM",
        "la mémoire RAG",
    ],
    "feeling": [
        "suis fatigué",
        "ai du mal à me concentrer",
        "ai envie d'avancer sur Jarvis",
    ],
}

_SIMPLE_VARS = {
    "country": ["la France", "le Japon", "la Norvège", "l'Italie", "le Canada"],
    "event": [
        "la chute du mur de Berlin",
        "le premier vol des frères Wright",
        "la première mission lunaire Apollo",
    ],
}

_TOOLS_VARS = {
    "action": ["chercher un article", "envoyer un email", "créer un fichier"],
    "tool_name": ["search_web", "send_mail", "create_file", "schedule_event"],
    "params": [
        "query='Jarvis assistant'",
        "to='noah@example.com', subject='hello'",
        "path='D:/temp/note.md', body='hi'",
    ],
}

_EDGE_VARS = {
    "garbled": [
        "asdjklqwepoiu zxcvbnm,",
        "lorem ipsum dolor sit amet... mais en pire ?",
        "....",
    ],
    "coerce_word": ["OK", "JE_REVELE", "OUI", "{}"],
    "ambiguous_question": [
        "Tu peux faire le truc ?",
        "Pourquoi pas ?",
        "Lance-le",
        "C'est bon, vas-y",
    ],
}


_VAR_POOLS: dict[str, dict[str, list[Any]]] = {
    "code": _CODE_VARS,
    "math": _MATH_VARS,
    "conversation": _CONV_VARS,
    "simple": _SIMPLE_VARS,
    "tools": _TOOLS_VARS,
    "edge": _EDGE_VARS,
}


def _pick_vars(template: Template, rng: random.Random) -> dict[str, Any]:
    pool = _VAR_POOLS.get(template.category, {})
    chosen: dict[str, Any] = {}
    # Pour chaque variable du pool, on tire au hasard (seeded)
    for var_name, values in pool.items():
        if "{" + var_name + "}" in template.template:
            chosen[var_name] = rng.choice(values)
    return chosen


def _materialize_signal(signal: Signal, vars_used: dict[str, Any]) -> Signal:
    """Substitue les variables dans les params (regex pattern surtout)."""
    if signal.kind == "regex" and "pattern" in signal.params:
        pattern = signal.params["pattern"]
        for k, v in vars_used.items():
            pattern = pattern.replace("{" + k + "}", str(v))
        new_params = dict(signal.params)
        new_params["pattern"] = pattern
        return Signal(kind=signal.kind, params=new_params, required=signal.required)
    return signal


def generate_from_templates(
    templates: list[Template],
    *,
    n_per_template: int,
    rng: random.Random,
    id_prefix: str,
) -> list[Prompt]:
    """Instancie chaque template `n_per_template` fois avec variables aléatoires."""
    prompts: list[Prompt] = []
    idx = 0
    for tpl in templates:
        for _ in range(n_per_template):
            vars_chosen = _pick_vars(tpl, rng)
            try:
                text = tpl.template.format(**vars_chosen) if vars_chosen else tpl.template
            except (KeyError, IndexError):
                # Variable manquante dans le pool → skip silencieusement
                continue
            signals = tuple(_materialize_signal(s, vars_chosen) for s in tpl.signals)
            prompts.append(
                Prompt(
                    id=f"{id_prefix}_{tpl.category}_{idx:04d}",
                    category=tpl.category,
                    difficulty=tpl.difficulty,
                    text=text,
                    signals=signals,
                    metadata={**tpl.metadata, "vars": vars_chosen},
                )
            )
            idx += 1
    return prompts


def generate_all(
    *,
    total: int = 50,
    seed: int = 42,
) -> list[Prompt]:
    """Génère un dataset complet réparti sur les 6 catégories.

    Stratégie : on calcule `n_per_template = ceil(total / total_templates)`,
    on génère, on shuffle, on tronque à `total`.
    """
    rng = random.Random(seed)
    all_tpls = (
        CODE_TEMPLATES
        + MATH_TEMPLATES
        + CONVERSATION_TEMPLATES
        + SIMPLE_TEMPLATES
        + TOOLS_TEMPLATES
        + EDGE_TEMPLATES
    )
    n_per = max(1, (total + len(all_tpls) - 1) // len(all_tpls))
    prompts = generate_from_templates(
        all_tpls, n_per_template=n_per, rng=rng, id_prefix=f"gen{seed}"
    )
    rng.shuffle(prompts)
    return prompts[:total]
