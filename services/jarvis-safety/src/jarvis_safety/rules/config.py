"""Chargement de la config rules.yaml et exposition typée.

Le fichier `config/rules.yaml` (gitignored, perso à Noah) déclare toutes les
règles. Cf recherche 101 pour le schéma. Si le fichier n'existe pas, on
utilise des défauts safe (blacklist minimale, whitelist `~/Documents/Jarvis`,
audit en `.local/audit_log.db`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_BLACKLIST = [
    r"^\s*format\b",
    r"\brm\s+-rf\s+/(?:\s|$)",
    r"\brm\s+-rf\s+/\*",
    r"\bshutdown\b.*\s/s\b",
    r"\breg\s+delete\b.*HKLM",
    r"\bDel\s+/[FQS]\b.*Windows\\System32",
]

DEFAULT_REDACT_PATTERNS = [
    r"sk-ant-[a-zA-Z0-9_-]{20,}",
    r"sk-[a-zA-Z0-9]{20,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"gho_[a-zA-Z0-9]{36}",
    r"github_pat_[a-zA-Z0-9_]{50,}",
    r"\b[a-f0-9]{32}\b",  # MD5 / common API key hex
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
]


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    blacklist_commands: list[str] = field(default_factory=lambda: list(DEFAULT_BLACKLIST))
    whitelist_write_paths: list[str] = field(default_factory=list)
    confirm_delete_files_count: int = 10
    confirm_delete_size_mb: int = 100
    pc_actions_per_min: int = 30
    emails_per_hour: int = 5


@dataclass(frozen=True, slots=True)
class PrivacyConfig:
    cloud_disabled: bool = True
    network_whitelist: list[str] = field(default_factory=list)
    audio_retention_hours: int = 24
    redact_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_REDACT_PATTERNS))


@dataclass(frozen=True, slots=True)
class AuditConfig:
    log_path: str = ".local/audit_log.db"
    retention_days: int = 90


@dataclass(frozen=True, slots=True)
class QuotasConfig:
    max_session_tokens: int = 100_000
    anti_loop_window_sec: int = 60
    anti_loop_threshold: int = 3


@dataclass(frozen=True, slots=True)
class RulesConfig:
    version: int = 1
    security: SecurityConfig = field(default_factory=SecurityConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    quotas: QuotasConfig = field(default_factory=QuotasConfig)

    @classmethod
    def from_dict(cls, data: dict) -> RulesConfig:
        sec_data = data.get("security", {})
        priv_data = data.get("privacy", {})
        audit_data = data.get("audit", {})
        quotas_data = data.get("quotas", {})

        return cls(
            version=int(data.get("version", 1)),
            security=SecurityConfig(
                blacklist_commands=sec_data.get("blacklist_commands", list(DEFAULT_BLACKLIST)),
                whitelist_write_paths=sec_data.get("whitelist_write_paths", []),
                confirm_delete_files_count=int(
                    sec_data.get("confirm_threshold", {}).get("delete_files_count", 10)
                ),
                confirm_delete_size_mb=int(
                    sec_data.get("confirm_threshold", {}).get("delete_size_mb", 100)
                ),
                pc_actions_per_min=int(
                    sec_data.get("rate_limit", {}).get("pc_actions_per_min", 30)
                ),
                emails_per_hour=int(sec_data.get("rate_limit", {}).get("emails_per_hour", 5)),
            ),
            privacy=PrivacyConfig(
                cloud_disabled=bool(priv_data.get("cloud_disabled", True)),
                network_whitelist=priv_data.get("network_whitelist", []),
                audio_retention_hours=int(priv_data.get("audio_retention_hours", 24)),
                redact_patterns=priv_data.get("redact_patterns", list(DEFAULT_REDACT_PATTERNS)),
            ),
            audit=AuditConfig(
                log_path=str(audit_data.get("log_path", ".local/audit_log.db")),
                retention_days=int(audit_data.get("retention_days", 90)),
            ),
            quotas=QuotasConfig(
                max_session_tokens=int(quotas_data.get("max_session_tokens", 100_000)),
                anti_loop_window_sec=int(quotas_data.get("anti_loop_window_sec", 60)),
                anti_loop_threshold=int(quotas_data.get("anti_loop_threshold", 3)),
            ),
        )

    @classmethod
    def from_yaml(cls, path: Path | str) -> RulesConfig:
        p = Path(path)
        if not p.exists():
            return cls()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)


def load_rules_config(path: Path | str | None = None) -> RulesConfig:
    """Charge la config depuis le path donné, ou `config/rules.yaml` à la racine repo."""
    if path is None:
        path = Path("config/rules.yaml")
    return RulesConfig.from_yaml(path)
