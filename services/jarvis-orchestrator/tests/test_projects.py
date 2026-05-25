"""Tests du module orchestrator.projects (scanner + commandes)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orchestrator.projects.commands import cmd_idee, cmd_projects, cmd_standup, cmd_status
from orchestrator.projects.scanner import ProjectScanner


def _make_git_repo(path: Path, *, dirty: bool = False) -> None:
    """Crée un repo git minimal pour les tests."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git absent")
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@x.io"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)
    (path / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    if dirty:
        (path / "wip.txt").write_text("work in progress", encoding="utf-8")


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def test_scanner_empty_root_returns_empty(tmp_path: Path) -> None:
    scanner = ProjectScanner(tmp_path)
    assert scanner.scan() == []


def test_scanner_lists_subdirs(tmp_path: Path) -> None:
    (tmp_path / "proj_a").mkdir()
    (tmp_path / "proj_b").mkdir()
    (tmp_path / "not_a_dir.txt").write_text("ignore", encoding="utf-8")
    scanner = ProjectScanner(tmp_path)
    projects = scanner.scan()
    names = sorted(p.name for p in projects)
    assert names == ["proj_a", "proj_b"]


def test_scanner_skips_hidden_by_default(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / "proj").mkdir()
    projects = ProjectScanner(tmp_path).scan()
    assert [p.name for p in projects] == ["proj"]


def test_scanner_detects_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "myrepo"
    _make_git_repo(repo)
    projects = ProjectScanner(tmp_path).scan()
    p = next(x for x in projects if x.name == "myrepo")
    assert p.is_git_repo is True
    assert p.current_branch in {"main", "master"}
    assert p.dirty_files == 0


def test_scanner_counts_dirty_files(tmp_path: Path) -> None:
    repo = tmp_path / "dirty_repo"
    _make_git_repo(repo, dirty=True)
    projects = ProjectScanner(tmp_path).scan()
    p = next(x for x in projects if x.name == "dirty_repo")
    assert p.dirty_files >= 1


def test_scanner_size_estimate(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "file1.txt").write_text("X" * 100, encoding="utf-8")
    (proj / "file2.txt").write_text("Y" * 50, encoding="utf-8")
    projects = ProjectScanner(tmp_path).scan()
    p = projects[0]
    assert p.size_bytes_estimate >= 150


def test_scanner_handles_nonexistent_root(tmp_path: Path) -> None:
    scanner = ProjectScanner(tmp_path / "nope")
    assert scanner.scan() == []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def test_cmd_projects_lists(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    out = cmd_projects(ProjectScanner(tmp_path))
    assert "alpha" in out
    assert "beta" in out
    assert "2 projets" in out


def test_cmd_projects_empty(tmp_path: Path) -> None:
    out = cmd_projects(ProjectScanner(tmp_path))
    assert "aucun projet" in out


def test_cmd_status_found(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    out = cmd_status("alpha", scanner=ProjectScanner(tmp_path))
    assert "alpha" in out
    assert "chemin" in out


def test_cmd_status_not_found(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    out = cmd_status("zzz", scanner=ProjectScanner(tmp_path))
    assert "introuvable" in out
    assert "alpha" in out  # liste des dispos


def test_cmd_status_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "MyProject").mkdir()
    out = cmd_status("myproject", scanner=ProjectScanner(tmp_path))
    assert "MyProject" in out


def test_cmd_standup_no_recent_activity(tmp_path: Path) -> None:
    # Au moins un projet pour que cmd_standup ne renvoie pas le message "aucun à résumer"
    (tmp_path / "stale_proj").mkdir()
    out = cmd_standup(ProjectScanner(tmp_path))
    assert "Standup" in out
    # Aucun projet n'est touché récemment ni dirty
    assert "touché" in out


def test_cmd_standup_with_dirty_repo(tmp_path: Path) -> None:
    _make_git_repo(tmp_path / "wip", dirty=True)
    out = cmd_standup(ProjectScanner(tmp_path))
    assert "wip" in out
    assert "modifs non commitées" in out


def test_cmd_idee_captures_text() -> None:
    out = cmd_idee("ajouter mode focus auto-lumières")
    assert "ajouter mode focus" in out
    assert "Idée capturée" in out


def test_cmd_idee_refuses_empty() -> None:
    assert "idée vide" in cmd_idee("")
    assert "idée vide" in cmd_idee("   ")
