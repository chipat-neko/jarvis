"""Tests du ToolProxy : whitelist / blacklist / rate limit / audit."""

from __future__ import annotations

from pathlib import Path

from jarvis_safety.rules.audit import AuditLogger
from jarvis_safety.rules.blacklist import BlacklistChecker
from jarvis_safety.rules.paths import PathWhitelist
from jarvis_safety.rules.rate_limit import RateLimiter
from jarvis_tools.mcp_client import MCPToolResult
from jarvis_tools.tool_proxy import ToolProxy, ToolProxyConfig


def _success_callable(name: str, args: dict) -> MCPToolResult:
    return MCPToolResult(ok=True, content=[{"type": "text", "text": "OK"}])


def _failure_callable(name: str, args: dict) -> MCPToolResult:
    return MCPToolResult(ok=False, error="tool exploded")


def _raising_callable(name: str, args: dict) -> MCPToolResult:
    raise RuntimeError("subprocess died")


# ---------------------------------------------------------------------------
# No-op proxy (tous les hooks désactivés) → passe tout
# ---------------------------------------------------------------------------


def test_noop_proxy_calls_callable() -> None:
    proxy = ToolProxy(_success_callable, config=ToolProxyConfig())
    res = proxy.call("read_file", {"path": "/tmp/x"})
    assert res.ok is True
    assert res.result is not None and res.result.text() == "OK"
    assert res.refused is False


# ---------------------------------------------------------------------------
# PathWhitelist
# ---------------------------------------------------------------------------


def test_path_whitelist_refuses_outside(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    whitelist = PathWhitelist([str(allowed)])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(path_whitelist=whitelist),
    )
    res = proxy.call("read_file", {"path": "/etc/passwd"})
    assert res.ok is False
    assert res.refused is True
    assert "hors whitelist" in (res.reason or "")


def test_path_whitelist_allows_inside(tmp_path: Path) -> None:
    whitelist = PathWhitelist([str(tmp_path)])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(path_whitelist=whitelist),
    )
    res = proxy.call("read_file", {"path": str(tmp_path / "ok.txt")})
    assert res.ok is True


def test_path_whitelist_checks_paths_list_arg(tmp_path: Path) -> None:
    whitelist = PathWhitelist([str(tmp_path)])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(path_whitelist=whitelist),
    )
    # Un seul path interdit dans la liste → refus
    res = proxy.call(
        "batch_read",
        {"paths": [str(tmp_path / "a"), "/etc/shadow"]},
    )
    assert res.refused is True


# ---------------------------------------------------------------------------
# Blacklist
# ---------------------------------------------------------------------------


def test_blacklist_blocks_match() -> None:
    blacklist = BlacklistChecker(patterns=[r"\brm\s+-rf\s+/"])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(blacklist=blacklist),
    )
    res = proxy.call("shell", {"command": "rm -rf / now"})
    assert res.refused is True
    assert res.matched_pattern is not None


def test_blacklist_passes_safe_string() -> None:
    blacklist = BlacklistChecker(patterns=[r"\brm\s+-rf\s+/"])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(blacklist=blacklist),
    )
    res = proxy.call("shell", {"command": "ls -la"})
    assert res.ok is True


def test_blacklist_recursive_dict_check() -> None:
    blacklist = BlacklistChecker(patterns=[r"\bformat\b"])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(blacklist=blacklist),
    )
    # Pattern caché dans une sous-structure
    res = proxy.call("complex", {"opts": {"cmd": "format C:"}})
    assert res.refused is True


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_rate_limit_refuses_after_quota() -> None:
    limiter = RateLimiter({"mcp.spam": (2, 60.0)})
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(rate_limiter=limiter),
    )
    assert proxy.call("spam", {}).ok is True
    assert proxy.call("spam", {}).ok is True
    res = proxy.call("spam", {})
    assert res.refused is True
    assert "rate limit" in (res.reason or "")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def test_audit_logs_success(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    proxy = ToolProxy(_success_callable, config=ToolProxyConfig(audit=audit))
    proxy.call("echo", {"text": "hi"})
    events = audit.recent()
    # Un event "before" + un event "after"
    assert len(events) == 2
    assert all(e["action"] == "tool_call" for e in events)
    assert any(e["payload"].get("phase") == "after" for e in events)


def test_audit_logs_refusal(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    blacklist = BlacklistChecker(patterns=[r"DROP TABLE"])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(audit=audit, blacklist=blacklist),
    )
    proxy.call("sql", {"query": "DROP TABLE users"})
    events = audit.recent()
    assert len(events) == 1
    assert events[0]["action"] == "refused_blacklist"
    assert events[0]["status"] == "refused"


def test_audit_logs_exception(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    proxy = ToolProxy(_raising_callable, config=ToolProxyConfig(audit=audit))
    res = proxy.call("bug", {})
    assert res.ok is False
    assert "exception" in (res.reason or "")
    # 2 events : before (ok) + after (error)
    events = audit.recent()
    statuses = sorted(e["status"] for e in events)
    assert statuses == ["error", "ok"]


# ---------------------------------------------------------------------------
# Callable retourne ok=False → propagation
# ---------------------------------------------------------------------------


def test_failure_callable_propagated() -> None:
    proxy = ToolProxy(_failure_callable, config=ToolProxyConfig())
    res = proxy.call("any", {})
    assert res.ok is False
    assert res.reason == "tool exploded"


# ---------------------------------------------------------------------------
# Long args sanitization
# ---------------------------------------------------------------------------


def test_audit_truncates_long_strings(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    proxy = ToolProxy(_success_callable, config=ToolProxyConfig(audit=audit))
    huge = "x" * 1000
    proxy.call("write", {"content": huge})
    events = audit.recent()
    payload = events[0]["payload"]
    assert "truncated" in payload["args"]["content"]


# ---------------------------------------------------------------------------
# Custom path_argument_keys
# ---------------------------------------------------------------------------


def test_custom_path_keys(tmp_path: Path) -> None:
    whitelist = PathWhitelist([str(tmp_path)])
    proxy = ToolProxy(
        _success_callable,
        config=ToolProxyConfig(
            path_whitelist=whitelist,
            path_argument_keys=("custom_path",),
        ),
    )
    res = proxy.call("any", {"custom_path": "/etc/passwd"})
    assert res.refused is True
