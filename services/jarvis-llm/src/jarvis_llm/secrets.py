"""Helpers pour récupérer les secrets (clés API, tokens) hors du code.

Ordre de priorité :
1. Keyring OS (Windows Credential Manager / macOS Keychain / GNOME Keyring)
2. Variable d'environnement (fallback dev / CI)
3. None (à l'appelant de gérer)

Convention pour stocker une clé Anthropic dans le keyring Windows :

    python -c "import keyring; keyring.set_password('jarvis', 'anthropic_api_key', 'sk-ant-...')"

ou via le script scripts/setup_keyring.ps1.
"""

from __future__ import annotations

import os

KEYRING_SERVICE = "jarvis"
ANTHROPIC_KEY_NAME = "anthropic_api_key"
ANTHROPIC_ENV_VAR = "ANTHROPIC_API_KEY"


def get_anthropic_api_key() -> str | None:
    """Retourne la clé Anthropic depuis keyring, puis env var, sinon None.

    keyring est importé lazy pour éviter une dépendance dure côté tests
    (les tests qui mockent ce module n'ont pas besoin de keyring).
    """
    try:
        import keyring  # noqa: PLC0415 — lazy import (keyring optionnel)

        stored = keyring.get_password(KEYRING_SERVICE, ANTHROPIC_KEY_NAME)
        if stored:
            return stored
    except Exception:
        pass

    return os.environ.get(ANTHROPIC_ENV_VAR) or None


def require_anthropic_api_key() -> str:
    """Identique à get_anthropic_api_key mais lève si rien n'est trouvé."""
    key = get_anthropic_api_key()
    if not key:
        raise RuntimeError(
            "Clé API Anthropic introuvable. Stocke-la via :\n"
            '  python -c "import keyring; '
            f"keyring.set_password('{KEYRING_SERVICE}', '{ANTHROPIC_KEY_NAME}', 'sk-ant-...')\"\n"
            f"ou définis la variable d'environnement {ANTHROPIC_ENV_VAR}."
        )
    return key
