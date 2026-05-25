"""Tests des Q/R answerers (files, git, system)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.q_and_a import FilesAnswerer, GitAnswerer, SystemAnswerer

# ---------------------------------------------------------------------------
# FilesAnswerer
# ---------------------------------------------------------------------------


def _allow_all(_p) -> bool:
    return True


def _allow_none(_p) -> bool:
    return False


def test_files_find_basic(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "c.md").write_text("doc", encoding="utf-8")

    fa = FilesAnswerer(_allow_all)
    res = fa.find("*.py", root=tmp_path)
    assert res.ok is True
    assert res.operation == "find"
    names = sorted(Path(m.path).name for m in res.matches)
    assert names == ["a.py", "b.py"]


def test_files_find_refused_if_root_not_whitelisted(tmp_path: Path) -> None:
    fa = FilesAnswerer(_allow_none)
    res = fa.find("*.py", root=tmp_path)
    assert res.ok is False
    assert "whitelist" in res.reason.lower()


def test_files_find_refused_if_root_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    fa = FilesAnswerer(_allow_all)
    res = fa.find("*", root=f)
    assert res.ok is False


def test_files_grep_finds_matches(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("hello world\nfoo bar\nhello again", encoding="utf-8")
    (tmp_path / "y.txt").write_text("nothing here", encoding="utf-8")

    fa = FilesAnswerer(_allow_all)
    res = fa.grep("hello", root=tmp_path)
    assert res.ok is True
    assert len(res.matches) == 2
    assert all(m.line_content and "hello" in m.line_content for m in res.matches)


def test_files_grep_empty_text(tmp_path: Path) -> None:
    fa = FilesAnswerer(_allow_all)
    res = fa.grep("", root=tmp_path)
    assert res.ok is False


def test_files_read(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("contenu utile", encoding="utf-8")
    fa = FilesAnswerer(_allow_all)
    res = fa.read(p)
    assert res.ok is True
    assert res.text == "contenu utile"


def test_files_read_refused_if_outside_whitelist(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("x", encoding="utf-8")
    fa = FilesAnswerer(_allow_none)
    res = fa.read(p)
    assert res.ok is False


def test_files_read_too_big(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_text("X" * 1000, encoding="utf-8")
    fa = FilesAnswerer(_allow_all, max_file_size_bytes=500)
    res = fa.read(p)
    assert res.ok is False
    assert "trop gros" in res.reason


def test_files_read_inexistant(tmp_path: Path) -> None:
    fa = FilesAnswerer(_allow_all)
    res = fa.read(tmp_path / "nope.txt")
    assert res.ok is False
    assert "inexistant" in res.reason


# ---------------------------------------------------------------------------
# GitAnswerer
# ---------------------------------------------------------------------------


def test_git_status_on_repo(tmp_path: Path) -> None:
    """On utilise le repo Jarvis lui-même (qui doit être un git repo)."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git pas installé sur cette machine")
    # On part de notre repo Jarvis (cwd lors des tests)
    answerer = GitAnswerer(repo_path=Path.cwd())
    res = answerer.status()
    assert res.ok is True
    assert res.operation == "status"


def test_git_log(tmp_path: Path) -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git pas installé")
    answerer = GitAnswerer(repo_path=Path.cwd())
    res = answerer.log(max_count=3)
    assert res.ok is True
    assert len(res.lines) <= 3


def test_git_current_branch() -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git pas installé")
    answerer = GitAnswerer(repo_path=Path.cwd())
    res = answerer.current_branch()
    assert res.ok is True
    assert res.text.strip() in {"main", "master", "HEAD"} or len(res.text.strip()) > 0


def test_git_on_non_repo_fails(tmp_path: Path) -> None:
    """Sur un dossier qui n'est pas un repo git, status retourne ok=False."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git pas installé")
    answerer = GitAnswerer(repo_path=tmp_path)
    res = answerer.status()
    assert res.ok is False
    assert "git" in res.reason.lower() or "not a git" in res.reason.lower()


# ---------------------------------------------------------------------------
# SystemAnswerer
# ---------------------------------------------------------------------------


def test_system_cpu() -> None:
    sys_answerer = SystemAnswerer()
    res = sys_answerer.cpu()
    # psutil installé localement, mais peut manquer en CI minimaliste
    if not res.ok:
        pytest.skip("psutil non installé dans cet env")
    assert "percent" in res.data
    assert isinstance(res.data["count_logical"], int)


def test_system_memory() -> None:
    sys_answerer = SystemAnswerer()
    res = sys_answerer.memory()
    if not res.ok:
        pytest.skip("psutil non installé")
    assert res.data["total_gb"] > 0
    assert 0 <= res.data["percent"] <= 100


def test_system_ollama_status_when_running() -> None:
    """Skip si Ollama n'est pas joignable (la CI ne l'aura pas)."""
    sys_answerer = SystemAnswerer()
    res = sys_answerer.ollama_status()
    if not res.ok:
        pytest.skip("Ollama non joignable, attendu en CI")
    assert res.data["status"] == "running"
