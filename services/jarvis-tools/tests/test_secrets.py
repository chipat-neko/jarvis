"""Tests des helpers secrets + de la résolution `$keyring:name` dans le registry."""

from __future__ import annotations

from unittest.mock import patch

from jarvis_tools.mcp_registry import MCPServerConfig
from jarvis_tools.secrets import get_secret, set_secret


def test_get_secret_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("ABSENT_SECRET", raising=False)
    with patch("keyring.get_password", return_value=None):
        assert get_secret("absent_secret") is None


def test_get_secret_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("FALLBACK_KEY", "from-env")
    # Patch keyring pour qu'il retourne None
    with patch("keyring.get_password", return_value=None):
        assert get_secret("fallback_key") == "from-env"


def test_get_secret_prefers_keyring_over_env(monkeypatch) -> None:
    monkeypatch.setenv("MY_KEY", "from-env")
    with patch("keyring.get_password", return_value="from-keyring"):
        assert get_secret("my_key") == "from-keyring"


def test_get_secret_custom_env_var(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_ENV", "custom-value")
    with patch("keyring.get_password", return_value=None):
        assert get_secret("anything", env_var="CUSTOM_ENV") == "custom-value"


def test_set_secret_via_mock() -> None:
    with patch("keyring.set_password") as mock_set:
        assert set_secret("my_key", "value") is True
        mock_set.assert_called_once_with("jarvis", "my_key", "value")


def test_set_secret_returns_false_on_backend_error() -> None:
    with patch("keyring.set_password", side_effect=RuntimeError("no backend")):
        assert set_secret("my_key", "value") is False


# ---------------------------------------------------------------------------
# Registry $keyring:NAME substitution
# ---------------------------------------------------------------------------


def test_resolved_env_substitutes_keyring(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with patch("keyring.get_password", return_value="BSA-test-key"):
        cfg = MCPServerConfig(
            name="x",
            command="echo",
            env={"BRAVE_API_KEY": "$keyring:brave_api_key"},
        )
        assert cfg.resolved_env() == {"BRAVE_API_KEY": "BSA-test-key"}


def test_resolved_env_keyring_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("BRAVE_API_KEY", "from-env")
    with patch("keyring.get_password", return_value=None):
        cfg = MCPServerConfig(
            name="x",
            command="echo",
            env={"BRAVE_API_KEY": "$keyring:brave_api_key"},
        )
        # keyring vide → fallback env var BRAVE_API_KEY (upper de la clé)
        assert cfg.resolved_env() == {"BRAVE_API_KEY": "from-env"}


def test_resolved_env_keyring_keeps_raw_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("NEVER_SET", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with patch("keyring.get_password", return_value=None):
        cfg = MCPServerConfig(
            name="x",
            command="echo",
            env={"K": "$keyring:never_set"},
        )
        # Aucune source → garde la string brute
        assert cfg.resolved_env() == {"K": "$keyring:never_set"}
