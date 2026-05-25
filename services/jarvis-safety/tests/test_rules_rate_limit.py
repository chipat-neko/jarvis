"""Tests du rate limiter token bucket."""

from __future__ import annotations

import time

from jarvis_safety.rules.rate_limit import RateLimiter


def test_under_limit_allowed() -> None:
    limiter = RateLimiter({"pc_action": (5, 60)})
    for _ in range(5):
        assert limiter.check_and_consume("pc_action").allowed is True


def test_over_limit_refused() -> None:
    limiter = RateLimiter({"pc_action": (3, 60)})
    for _ in range(3):
        assert limiter.check_and_consume("pc_action").allowed is True
    res = limiter.check_and_consume("pc_action")
    assert res.allowed is False
    assert "rate limit" in res.reason.lower()
    assert res.count_in_window == 3
    assert res.limit == 3


def test_separate_categories_independent() -> None:
    limiter = RateLimiter({"a": (2, 60), "b": (5, 60)})
    limiter.check_and_consume("a")
    limiter.check_and_consume("a")
    assert limiter.check_and_consume("a").allowed is False

    # b est dans une autre catégorie, indépendant
    for _ in range(5):
        assert limiter.check_and_consume("b").allowed is True


def test_unknown_category_pass_through() -> None:
    limiter = RateLimiter({"a": (1, 60)})
    res = limiter.check_and_consume("inexistant")
    assert res.allowed is True
    assert "pass-through" in res.reason.lower()


def test_window_expiry_releases_tokens() -> None:
    # Fenêtre très courte pour tester l'expiration
    limiter = RateLimiter({"fast": (2, 1)})
    assert limiter.check_and_consume("fast").allowed is True
    assert limiter.check_and_consume("fast").allowed is True
    assert limiter.check_and_consume("fast").allowed is False

    # Attendre que la fenêtre passe
    time.sleep(1.1)
    assert limiter.check_and_consume("fast").allowed is True


def test_current_count(monkeypatch) -> None:
    limiter = RateLimiter({"x": (10, 60)})
    assert limiter.current_count("x") == 0
    limiter.check_and_consume("x")
    limiter.check_and_consume("x")
    assert limiter.current_count("x") == 2
    assert limiter.current_count("nope") == 0


def test_refused_does_not_consume() -> None:
    """Une action refusée ne doit pas consommer un token (sinon double pénalité)."""
    limiter = RateLimiter({"pc_action": (2, 60)})
    limiter.check_and_consume("pc_action")
    limiter.check_and_consume("pc_action")
    # Saturé, donc refus
    assert limiter.check_and_consume("pc_action").allowed is False
    # Le compteur ne doit pas être au-dessus de la limite
    assert limiter.current_count("pc_action") == 2
