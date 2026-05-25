"""Tests du routeur d'intent Q/R."""

from __future__ import annotations

import pytest

from orchestrator.q_and_a import Intent, IntentRouter


@pytest.fixture
def router() -> IntentRouter:
    return IntentRouter()


def test_classify_empty_prompt(router: IntentRouter) -> None:
    res = router.classify("")
    assert res.intent is Intent.NONE
    assert res.confidence == 0.0


def test_classify_whitespace_only(router: IntentRouter) -> None:
    res = router.classify("   \n\t  ")
    assert res.intent is Intent.NONE


def test_classify_files_intent(router: IntentRouter) -> None:
    res = router.classify("trouve les fichiers Python dans le dossier services")
    assert res.intent is Intent.FILES
    assert res.confidence > 0
    assert any(kw in res.matched_keywords for kw in ("fichier", "fichiers", "dossier"))


def test_classify_files_intent_english(router: IntentRouter) -> None:
    res = router.classify("find all the files in the src folder")
    assert res.intent is Intent.FILES


def test_classify_grep_is_files(router: IntentRouter) -> None:
    res = router.classify("peux-tu grep 'TODO' dans le repo ?")
    assert res.intent is Intent.FILES


def test_classify_git_intent(router: IntentRouter) -> None:
    res = router.classify("Quelle est la branche actuelle ? Et les derniers commits ?")
    assert res.intent is Intent.GIT
    assert "branche" in res.matched_keywords or "commits" in res.matched_keywords


def test_classify_git_status(router: IntentRouter) -> None:
    res = router.classify("Donne-moi le git status")
    assert res.intent is Intent.GIT


def test_classify_system_intent_cpu(router: IntentRouter) -> None:
    res = router.classify("Quelle est la charge CPU actuellement ?")
    assert res.intent is Intent.SYSTEM
    assert "cpu" in res.matched_keywords


def test_classify_system_intent_gpu(router: IntentRouter) -> None:
    res = router.classify("Combien de VRAM utilise le GPU ?")
    assert res.intent is Intent.SYSTEM


def test_classify_system_intent_ollama(router: IntentRouter) -> None:
    res = router.classify("Est-ce qu'Ollama tourne ?")
    assert res.intent is Intent.SYSTEM
    assert "ollama" in res.matched_keywords


def test_classify_none_for_generic_chat(router: IntentRouter) -> None:
    res = router.classify("Bonjour, comment vas-tu aujourd'hui ?")
    assert res.intent is Intent.NONE


def test_classify_none_for_unrelated_question(router: IntentRouter) -> None:
    res = router.classify("Quelle est la capitale de la France ?")
    assert res.intent is Intent.NONE


def test_classify_picks_best_when_ambiguous(router: IntentRouter) -> None:
    # 2 mots-clés files vs 1 git → files gagne
    res = router.classify("lis le fichier README et donne-moi le hash")
    assert res.intent is Intent.FILES


def test_classify_word_boundary_no_false_positive(router: IntentRouter) -> None:
    # 'cpu' ne doit pas matcher 'cpuid' ou 'occupé'
    res = router.classify("je suis occupé maintenant")
    assert res.intent is Intent.NONE


def test_classify_threshold_two_hits() -> None:
    strict_router = IntentRouter(threshold_min_hits=2)
    # 1 seul hit ("cpu") → NONE en mode strict
    res = strict_router.classify("Donne-moi le CPU ?")
    assert res.intent is Intent.NONE
    # 2 hits ("cpu" + "ram") → SYSTEM
    res = strict_router.classify("Donne-moi le CPU et la RAM")
    assert res.intent is Intent.SYSTEM


def test_confidence_normalized() -> None:
    router = IntentRouter()
    res = router.classify("trouve les fichiers")
    assert 0 < res.confidence <= 1.0
