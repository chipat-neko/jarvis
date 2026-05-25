"""Tests du whitelist de chemins."""

from __future__ import annotations

from pathlib import Path

from jarvis_safety.rules.paths import PathWhitelist


def test_path_in_whitelist_allowed(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "jarvis_work"
    allowed_dir.mkdir()
    wl = PathWhitelist([str(allowed_dir)])

    assert wl.is_allowed(allowed_dir / "subfile.txt") is True
    assert wl.is_allowed(allowed_dir / "sub" / "deep" / "file.md") is True


def test_path_outside_whitelist_refused(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "jarvis_work"
    forbidden = tmp_path / "other"
    allowed_dir.mkdir()
    forbidden.mkdir()
    wl = PathWhitelist([str(allowed_dir)])

    res = wl.check(forbidden / "file.txt")
    assert res.allowed is False
    assert "whitelist" in res.reason.lower() or "dehors" in res.reason.lower()


def test_path_traversal_blocked(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "jarvis_work"
    allowed_dir.mkdir()
    wl = PathWhitelist([str(allowed_dir)])

    # Tentative de remonter en arrière → résolu, donc en dehors
    suspect = allowed_dir / ".." / "evil.txt"
    res = wl.check(suspect)
    assert res.allowed is False


def test_empty_whitelist_refuses_all(tmp_path: Path) -> None:
    wl = PathWhitelist([])
    res = wl.check(tmp_path / "anywhere.txt")
    assert res.allowed is False
    assert "vide" in res.reason.lower()


def test_tilde_expansion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    target = tmp_path / "Docs"
    target.mkdir()
    wl = PathWhitelist(["~/Docs"])
    assert wl.is_allowed(target / "note.md") is True


def test_multiple_paths_in_whitelist(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    wl = PathWhitelist([str(a), str(b)])
    assert wl.is_allowed(a / "x.txt") is True
    assert wl.is_allowed(b / "y.txt") is True
    assert wl.is_allowed(tmp_path / "c" / "z.txt") is False
