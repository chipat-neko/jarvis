"""Registre des MCP servers configurés.

Charge `config/mcp.yaml` (gitignored) ou fallback sur les DEFAULTS minimaux.
Chaque entrée définit comment lancer un MCP server (binaire + args + env).

Format attendu :
    servers:
      filesystem:
        command: "npx"
        args: ["-y", "@modelcontextprotocol/server-filesystem", "D:/assistant_ai"]
        env:
          KEY: "value"
        enabled: true
      brave-search:
        command: "npx"
        args: ["-y", "@modelcontextprotocol/server-brave-search"]
        env:
          BRAVE_API_KEY: "$BRAVE_API_KEY"
        enabled: false  # désactivé tant que clé pas posée
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """Configuration d'un MCP server (process à lancer en sous-process stdio)."""

    name: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def resolved_env(self) -> dict[str, str]:
        """Résout les `$VAR` dans les valeurs depuis l'environnement courant."""
        out: dict[str, str] = {}
        for k, v in self.env.items():
            out[k] = _expand_env_vars(v)
        return out


@dataclass(frozen=True, slots=True)
class MCPRegistry:
    """Liste immuable de configs MCP servers."""

    servers: tuple[MCPServerConfig, ...] = ()

    @classmethod
    def empty(cls) -> MCPRegistry:
        return cls()

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> MCPRegistry:
        """Charge un fichier YAML. Si le fichier n'existe pas, retourne empty."""
        p = Path(yaml_path)
        if not p.exists():
            return cls.empty()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> MCPRegistry:
        """Parse un dict YAML-déserialisé en MCPRegistry."""
        servers_section = data.get("servers", {}) or {}
        configs: list[MCPServerConfig] = []
        for name, raw in servers_section.items():
            if not isinstance(raw, dict):
                continue
            args_raw = raw.get("args", [])
            args = tuple(str(a) for a in args_raw) if args_raw else ()
            env_raw = raw.get("env", {}) or {}
            env = {str(k): str(v) for k, v in env_raw.items()}
            configs.append(
                MCPServerConfig(
                    name=name,
                    command=str(raw.get("command", "")),
                    args=args,
                    env=env,
                    enabled=bool(raw.get("enabled", True)),
                )
            )
        return cls(servers=tuple(configs))

    def enabled_servers(self) -> tuple[MCPServerConfig, ...]:
        return tuple(s for s in self.servers if s.enabled)

    def get(self, name: str) -> MCPServerConfig | None:
        for s in self.servers:
            if s.name == name:
                return s
        return None

    def names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.servers)


_ENV_VAR_RE = re.compile(r"\$(\w+)|\$\{(\w+)\}")
_KEYRING_RE = re.compile(r"\$keyring:([\w.-]+)")


def _expand_env_vars(value: str) -> str:
    """Remplace les références à des secrets dans `value`.

    Supporte deux formes :
    - `$VAR` ou `${VAR}` → lu depuis `os.environ`
    - `$keyring:name` → lu depuis le keyring OS via `jarvis_tools.secrets`
        (avec fallback env var `NAME` si keyring vide).

    Si la référence ne résout à rien, la string brute est conservée.
    """

    # 1) keyring d'abord (sinon $keyring:foo serait mangé par $VAR matcher)
    def _keyring_replace(match: re.Match[str]) -> str:
        from jarvis_tools.secrets import get_secret  # noqa: PLC0415 — lazy

        name = match.group(1)
        value = get_secret(name)
        return value if value is not None else match.group(0)

    value = _KEYRING_RE.sub(_keyring_replace, value)

    # 2) env vars classiques
    def _env_replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return os.environ.get(name, match.group(0))

    return _ENV_VAR_RE.sub(_env_replace, value)
