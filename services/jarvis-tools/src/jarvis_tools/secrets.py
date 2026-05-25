"""Helpers pour récupérer des secrets (clés API, tokens) depuis le keyring OS.

Le keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service)
est la couche standard pour persister un secret sans le mettre dans un fichier
gitignored.

Pour Jarvis, on utilise la lib `keyring` (Python). Service = "jarvis", username =
nom logique du secret (ex `brave_api_key`, `github_pat`).

Fallback : si keyring échoue ou si la clé n'existe pas, on lit la variable
d'environnement correspondante (utile en CI / Docker).
"""

from __future__ import annotations

import os

SERVICE_NAME = "jarvis"


def get_secret(name: str, *, env_var: str | None = None) -> str | None:
    """Récupère un secret depuis le keyring, fallback env var.

    Args:
        name: identifiant logique du secret (ex "brave_api_key").
        env_var: nom de la var d'env à essayer si keyring échoue
            (par défaut `name.upper()`).
    """
    try:
        import keyring  # noqa: PLC0415 — lazy import (keyring est lent à charger)
    except ImportError:
        keyring = None  # type: ignore[assignment]

    if keyring is not None:
        try:
            value = keyring.get_password(SERVICE_NAME, name)
            if value:
                return value
        except Exception:
            # Backend keyring foireux (Linux sans Secret Service, etc.) → fallback env
            pass

    env_key = env_var or name.upper()
    return os.environ.get(env_key)


def set_secret(name: str, value: str) -> bool:
    """Stocke un secret dans le keyring. Retourne True si OK, False si keyring KO."""
    try:
        import keyring  # noqa: PLC0415
    except ImportError:
        return False
    try:
        keyring.set_password(SERVICE_NAME, name, value)
        return True
    except Exception:
        return False


def delete_secret(name: str) -> bool:
    """Supprime un secret du keyring. Retourne True si OK."""
    try:
        import keyring  # noqa: PLC0415
        import keyring.errors  # noqa: PLC0415
    except ImportError:
        return False
    try:
        keyring.delete_password(SERVICE_NAME, name)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
    except Exception:
        return False
