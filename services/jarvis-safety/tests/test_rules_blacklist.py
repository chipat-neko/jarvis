"""Tests de la blacklist de commandes."""

from __future__ import annotations

import pytest

from jarvis_safety.rules.blacklist import BlacklistChecker
from jarvis_safety.rules.config import DEFAULT_BLACKLIST


@pytest.fixture
def checker() -> BlacklistChecker:
    return BlacklistChecker(DEFAULT_BLACKLIST)


def test_format_command_refused(checker: BlacklistChecker) -> None:
    res = checker.check("format C:")
    assert res.matched is True
    assert "blacklist" in res.reason.lower()


def test_rm_rf_root_refused(checker: BlacklistChecker) -> None:
    assert checker.check("rm -rf /").matched is True
    assert checker.check("rm -rf /*").matched is True


def test_shutdown_refused(checker: BlacklistChecker) -> None:
    assert checker.check("shutdown /s /t 0").matched is True


def test_reg_delete_hklm_refused(checker: BlacklistChecker) -> None:
    assert checker.check("reg delete HKLM\\Software\\Test").matched is True


def test_safe_commands_allowed(checker: BlacklistChecker) -> None:
    assert checker.is_allowed("ls -la") is True
    assert checker.is_allowed("git status") is True
    assert checker.is_allowed("python -m pytest") is True
    assert checker.is_allowed("rm tmp_file.txt") is True  # pas rm -rf /


def test_case_insensitive(checker: BlacklistChecker) -> None:
    assert checker.check("FORMAT C:").matched is True
    assert checker.check("ShutDown /S /T 0").matched is True


def test_extra_spaces_handled(checker: BlacklistChecker) -> None:
    assert checker.check("  format    C:  ").matched is True
    assert checker.check("rm  -rf   /").matched is True


def test_custom_blacklist() -> None:
    custom = BlacklistChecker([r"\bdocker\s+system\s+prune\b"])
    assert custom.check("docker system prune -a").matched is True
    assert custom.is_allowed("docker ps") is True


def test_empty_blacklist_allows_all() -> None:
    empty = BlacklistChecker([])
    assert empty.is_allowed("rm -rf /") is True  # vide = pass-through
