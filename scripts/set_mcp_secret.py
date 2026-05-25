"""Stocke une clé API MCP dans le keyring OS.

Usage :
    python -m scripts.set_mcp_secret --name brave_api_key --value "BSA..."
    python -m scripts.set_mcp_secret --name github_pat --value "ghp_..."

Le secret est stocké sous le service "jarvis" + username = `--name`.
Les MCP servers le retrouvent automatiquement via `jarvis_tools.secrets.get_secret`.

NE JAMAIS coller la clé en clair dans un fichier — c'est exactement pour ça
que keyring existe. Sur Windows, c'est stocké dans le Credential Manager.
"""

from __future__ import annotations

import argparse
import sys

from jarvis_tools.secrets import delete_secret, get_secret, set_secret


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stocke un secret MCP dans le keyring.")
    parser.add_argument("--name", required=True, help="nom logique (ex brave_api_key)")
    parser.add_argument("--value", default=None, help="valeur du secret (lue sur stdin si absent)")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="supprime le secret au lieu de le poser",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="vérifie juste si le secret est posé (n'affiche jamais la valeur)",
    )
    args = parser.parse_args(argv)

    if args.delete:
        ok = delete_secret(args.name)
        print(f"[secret] {'supprimé' if ok else 'introuvable'} : {args.name}", file=sys.stderr)
        return 0 if ok else 1

    if args.check:
        value = get_secret(args.name)
        if value:
            print(f"[secret] '{args.name}' présent ({len(value)} chars)", file=sys.stderr)
            return 0
        print(f"[secret] '{args.name}' ABSENT", file=sys.stderr)
        return 1

    value = args.value
    if value is None:
        try:
            value = input(f"Valeur pour {args.name} : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[secret] annulé", file=sys.stderr)
            return 2
    if not value:
        print("[secret] valeur vide refusée", file=sys.stderr)
        return 2

    if not set_secret(args.name, value):
        print("[secret] keyring indisponible — secret non posé", file=sys.stderr)
        return 3
    print(f"[secret] '{args.name}' posé dans le keyring ({len(value)} chars)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
