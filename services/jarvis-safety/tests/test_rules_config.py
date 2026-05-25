"""Tests du chargement de la config rules.yaml."""

from __future__ import annotations

from pathlib import Path

from jarvis_safety.rules.config import (
    DEFAULT_BLACKLIST,
    DEFAULT_REDACT_PATTERNS,
    RulesConfig,
    load_rules_config,
)


def test_defaults_when_no_file(tmp_path: Path) -> None:
    cfg = RulesConfig.from_yaml(tmp_path / "nope.yaml")
    assert cfg.version == 1
    assert cfg.security.blacklist_commands == DEFAULT_BLACKLIST
    assert cfg.privacy.cloud_disabled is True
    assert cfg.audit.retention_days == 90
    assert cfg.privacy.redact_patterns == DEFAULT_REDACT_PATTERNS


def test_from_dict_overrides(tmp_path: Path) -> None:
    data = {
        "version": 2,
        "security": {
            "blacklist_commands": [r"^foo"],
            "whitelist_write_paths": ["/tmp/jarvis"],
            "confirm_threshold": {"delete_files_count": 5},
            "rate_limit": {"pc_actions_per_min": 10},
        },
        "privacy": {
            "cloud_disabled": False,
            "network_whitelist": ["example.com"],
        },
        "audit": {"log_path": "/tmp/audit.db", "retention_days": 30},
        "quotas": {"max_session_tokens": 50_000},
    }
    cfg = RulesConfig.from_dict(data)
    assert cfg.version == 2
    assert cfg.security.blacklist_commands == [r"^foo"]
    assert cfg.security.whitelist_write_paths == ["/tmp/jarvis"]
    assert cfg.security.confirm_delete_files_count == 5
    assert cfg.security.pc_actions_per_min == 10
    assert cfg.privacy.cloud_disabled is False
    assert cfg.privacy.network_whitelist == ["example.com"]
    assert cfg.audit.retention_days == 30
    assert cfg.quotas.max_session_tokens == 50_000


def test_from_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: 1\n"
        "security:\n"
        "  whitelist_write_paths:\n"
        "    - /home/me/work\n"
        "audit:\n"
        "  log_path: /var/log/jarvis.db\n",
        encoding="utf-8",
    )
    cfg = RulesConfig.from_yaml(path)
    assert cfg.security.whitelist_write_paths == ["/home/me/work"]
    assert cfg.audit.log_path == "/var/log/jarvis.db"


def test_load_rules_config_default_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    # Pas de config/rules.yaml → défauts
    cfg = load_rules_config()
    assert cfg.audit.retention_days == 90
