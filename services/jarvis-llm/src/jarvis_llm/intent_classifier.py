"""Classifieur d'intent basique (heuristiques mot-clé).

MVP — sera remplacé par un classifier plus malin (modèle embedding ou
prompt classifier) aux sprints suivants. L'objectif ici est juste de router
correctement les requêtes évidentes.

Stratégie :
- match d'expressions régulières par catégorie, par priorité décroissante
- si rien ne matche → CONVERSATIONAL (fallback safe vers local)
"""

from __future__ import annotations

import re

from jarvis_llm.router import IntentClass

# Mots-clé qui dénoncent une demande de code (génération, refactor, debug...).
_CODE_PATTERNS = [
    r"\b(code|fonction|function|méthode|method|class|classe|module|script)\b",
    r"\b(refactor|debug|déb[ou]g(?:ue|gage)|implémente?r?|implement)\b",
    r"\b(python|rust|javascript|typescript|java|c\+\+|sql|html|css|bash)\b",
    r"\b(bug|erreur|stacktrace|exception|traceback)\b",
    r"```",  # bloc de code dans le prompt
]

# Outils / actions PC ou external (à un terme la couche tools s'en chargera).
_TOOL_USE_PATTERNS = [
    r"\b(ouvre|open|lance|launch|démarre|start)\b.*\b(app|application|navigateur|browser)\b",
    r"\b(spotify|gmail|notion|github|brave|google)\b",
    r"\b(joue?|play)\b.*\b(musique|music|chanson|song)\b",
    r"\b(recherche|search|google)\b",
    r"\b(envoie|send)\b.*\b(mail|email|message)\b",
]

# Reasoning / analyse / multi-step → cloud (Sonnet est nettement meilleur).
_COMPLEX_PATTERNS = [
    r"\b(explique|explain|pourquoi|why|comment fonctionne|how does)\b",
    r"\b(compare|différence|difference|vs|versus)\b",
    r"\b(analyse|résume|résum[eo]|summarize|synthèse|synthese)\b",
    r"\b(raisonne|reason|réfléchis|think|étapes?|steps?)\b",
    r"\b(planifie|plan|stratégie|strategy)\b",
]

# Questions courtes triviales → local sans hésiter.
_SIMPLE_PATTERNS = [
    r"\b(quelle heure|what time|heure|time)\b",
    r"\b(météo|weather)\b",
    r"\b(convertis|convert|combien|how many|how much)\b",
    r"\b(date|jour|today|aujourd['']hui)\b",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def classify(text: str) -> IntentClass:
    """Retourne la classe d'intent estimée pour le texte donné.

    Ordre de priorité : CODE > TOOL_USE > COMPLEX > SIMPLE > CONVERSATIONAL (fallback).
    """
    if not text or not text.strip():
        return IntentClass.CONVERSATIONAL

    if _matches_any(text, _CODE_PATTERNS):
        return IntentClass.CODE

    if _matches_any(text, _TOOL_USE_PATTERNS):
        return IntentClass.TOOL_USE

    if _matches_any(text, _COMPLEX_PATTERNS):
        return IntentClass.COMPLEX

    if _matches_any(text, _SIMPLE_PATTERNS):
        return IntentClass.SIMPLE

    return IntentClass.CONVERSATIONAL
