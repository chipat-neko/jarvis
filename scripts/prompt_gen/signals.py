"""Validateurs (signals) applicables sur une réponse de modèle.

Chaque Signal sait dire si la réponse satisfait son critère (`.check(text)`)
sans appel LLM. Permet du scoring déterministe pendant le bench.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Résultat d'application d'un signal."""

    passed: bool
    reason: str | None = None


class _SignalBase:
    """Interface des signaux (duck-typing)."""

    def check(self, text: str) -> CheckResult:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RegexMatchSignal(_SignalBase):
    """Vérifie qu'une regex match (au moins une fois) dans la réponse."""

    pattern: str
    flags: int = 0

    def check(self, text: str) -> CheckResult:
        try:
            compiled = re.compile(self.pattern, self.flags)
        except re.error as exc:
            return CheckResult(passed=False, reason=f"regex invalide: {exc}")
        if compiled.search(text):
            return CheckResult(passed=True)
        return CheckResult(passed=False, reason=f"pattern {self.pattern!r} non trouvé")


@dataclass(frozen=True, slots=True)
class AstParseSignal(_SignalBase):
    """Vérifie qu'un bloc de code (Python) parse via ast.parse.

    On extrait le premier bloc ```python ... ``` si présent, sinon on tente
    le texte brut.
    """

    language: str = "python"

    def check(self, text: str) -> CheckResult:
        code = _extract_code_block(text, self.language) or text
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return CheckResult(passed=False, reason=f"SyntaxError: {exc}")
        return CheckResult(passed=True)


@dataclass(frozen=True, slots=True)
class JsonParseSignal(_SignalBase):
    """Vérifie que la réponse contient du JSON valide.

    On extrait le premier bloc ```json ... ``` ou le premier objet/array de la
    réponse. Si rien ne parse, échec.
    """

    def check(self, text: str) -> CheckResult:
        block = _extract_code_block(text, "json")
        candidate = block if block is not None else _extract_first_json_like(text)
        if candidate is None:
            return CheckResult(passed=False, reason="aucun JSON détecté")
        try:
            json.loads(candidate)
        except json.JSONDecodeError as exc:
            return CheckResult(passed=False, reason=f"JSON invalide: {exc.msg}")
        return CheckResult(passed=True)


@dataclass(frozen=True, slots=True)
class LengthRangeSignal(_SignalBase):
    """Vérifie que la longueur de la réponse est dans un range."""

    min_chars: int = 0
    max_chars: int = 100_000

    def check(self, text: str) -> CheckResult:
        n = len(text)
        if n < self.min_chars:
            return CheckResult(passed=False, reason=f"trop court: {n} < {self.min_chars}")
        if n > self.max_chars:
            return CheckResult(passed=False, reason=f"trop long: {n} > {self.max_chars}")
        return CheckResult(passed=True)


def _extract_code_block(text: str, language: str) -> str | None:
    """Extrait le contenu du premier bloc ```<language> ... ```."""
    pattern = rf"```{re.escape(language)}\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


def _extract_first_json_like(text: str) -> str | None:
    """Tente de trouver le premier objet `{...}` ou array `[...]` balancé."""
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None
