"""ToolProxy : applique les règles safety AVANT chaque CallTool.

Chaque appel passe par les checks suivants, dans l'ordre :
1. **PathWhitelist** : si le tool a un argument `path` ou `paths`, on vérifie
   que chaque path est dans la whitelist.
2. **BlacklistChecker** : on inspecte les valeurs string des arguments pour
   matcher les patterns destructifs (`rm -rf /`, `format`, etc.).
3. **RateLimiter** : on consomme un token sur la catégorie du tool (par défaut
   `mcp.{tool_name}`).
4. **AuditLogger** : on logue un event AVANT et APRÈS l'appel (status ok / refused / error).

Le proxy ne sait PAS comment appeler le MCP server — c'est le caller qui passe
un `callable` qui prend (tool_name, arguments) et retourne MCPToolResult.
Permet de tester le proxy sans subprocess réel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from jarvis_safety.rules.audit import AuditEvent, AuditLogger
from jarvis_safety.rules.blacklist import BlacklistChecker
from jarvis_safety.rules.paths import PathWhitelist
from jarvis_safety.rules.rate_limit import RateLimiter
from jarvis_tools.mcp_client import MCPToolResult

ToolCallable = Callable[[str, dict], MCPToolResult]
"""Signature attendue : (tool_name, arguments) -> MCPToolResult."""


@dataclass(frozen=True, slots=True)
class ProxiedToolResult:
    """Résultat d'un appel passé par le ToolProxy."""

    ok: bool
    result: MCPToolResult | None = None
    refused: bool = False
    reason: str | None = None
    audit_event_id: int | None = None
    matched_pattern: str | None = None


@dataclass(frozen=True, slots=True)
class ToolProxyConfig:
    """Configuration des hooks safety actifs (None = hook désactivé)."""

    path_whitelist: PathWhitelist | None = None
    blacklist: BlacklistChecker | None = None
    rate_limiter: RateLimiter | None = None
    audit: AuditLogger | None = None
    actor: str = "noah"
    rate_limit_category_prefix: str = "mcp."
    path_argument_keys: tuple[str, ...] = field(default=("path", "paths", "filepath", "file_path"))


class ToolProxy:
    """Wrapper safety autour d'un callable d'appel MCP."""

    def __init__(self, tool_callable: ToolCallable, *, config: ToolProxyConfig) -> None:
        self._call = tool_callable
        self._cfg = config

    def call(self, tool_name: str, arguments: dict | None = None) -> ProxiedToolResult:
        args = arguments or {}

        # 1. PathWhitelist
        if self._cfg.path_whitelist is not None:
            bad_path = _first_disallowed_path(args, self._cfg)
            if bad_path is not None:
                return self._refuse(
                    tool_name,
                    args,
                    reason=f"chemin hors whitelist: {bad_path}",
                    action="refused_path",
                )

        # 2. Blacklist sur les valeurs string
        if self._cfg.blacklist is not None:
            bad_match = _first_blacklist_match(args, self._cfg.blacklist)
            if bad_match is not None:
                return self._refuse(
                    tool_name,
                    args,
                    reason=f"pattern blacklist matché: {bad_match}",
                    action="refused_blacklist",
                    matched_pattern=bad_match,
                )

        # 3. RateLimiter
        if self._cfg.rate_limiter is not None:
            category = f"{self._cfg.rate_limit_category_prefix}{tool_name}"
            check = self._cfg.rate_limiter.check_and_consume(category)
            if not check.allowed:
                return self._refuse(
                    tool_name,
                    args,
                    reason=f"rate limit dépassé sur {category}",
                    action="refused_rate_limit",
                )

        # 4. Appel + audit du succès / échec
        event_id = self._log(
            tool_name,
            args,
            action="tool_call",
            status="ok",
            extra={"phase": "before"},
        )
        try:
            result = self._call(tool_name, args)
        except Exception as exc:
            self._log(
                tool_name,
                args,
                action="tool_call",
                status="error",
                extra={"phase": "after", "exception": str(exc)},
            )
            return ProxiedToolResult(
                ok=False,
                reason=f"exception pendant CallTool: {exc}",
                audit_event_id=event_id,
            )
        status = "ok" if result.ok else "error"
        self._log(
            tool_name,
            args,
            action="tool_call",
            status=status,
            extra={"phase": "after", "result_ok": result.ok},
        )
        return ProxiedToolResult(
            ok=result.ok,
            result=result,
            reason=result.error if not result.ok else None,
            audit_event_id=event_id,
        )

    def _refuse(
        self,
        tool_name: str,
        args: dict,
        *,
        reason: str,
        action: str,
        matched_pattern: str | None = None,
    ) -> ProxiedToolResult:
        event_id = self._log(
            tool_name,
            args,
            action=action,
            status="refused",
            extra={"reason": reason},
        )
        return ProxiedToolResult(
            ok=False,
            refused=True,
            reason=reason,
            audit_event_id=event_id,
            matched_pattern=matched_pattern,
        )

    def _log(
        self,
        tool_name: str,
        args: dict,
        *,
        action: str,
        status: str,
        extra: dict | None = None,
    ) -> int | None:
        if self._cfg.audit is None:
            return None
        payload = {
            "tool": tool_name,
            "args": _sanitize_for_audit(args),
            **(extra or {}),
        }
        return self._cfg.audit.log(
            AuditEvent(
                actor=self._cfg.actor,
                action=action,
                payload=payload,
                status=status,
            )
        )


def _first_disallowed_path(args: dict, cfg: ToolProxyConfig) -> str | None:
    """Retourne le premier path interdit trouvé dans args, ou None."""
    if cfg.path_whitelist is None:
        return None
    for key in cfg.path_argument_keys:
        if key not in args:
            continue
        value = args[key]
        candidates = value if isinstance(value, list) else [value]
        for p in candidates:
            if isinstance(p, str | bytes) and not cfg.path_whitelist.is_allowed(p):
                return str(p)
    return None


def _first_blacklist_match(args: dict, blacklist: BlacklistChecker) -> str | None:
    """Cherche un match blacklist dans les valeurs string."""
    for value in _iter_strings(args):
        match = blacklist.check(value)
        if match.matched:
            return match.pattern
    return None


def _iter_strings(obj: object):
    """Itère récursivement sur toutes les strings d'un dict / list / scalaire."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            yield from _iter_strings(v)


_AUDIT_VALUE_MAX = 500


def _sanitize_for_audit(args: dict) -> dict:
    """Tronque les très longues valeurs pour pas spammer l'audit log."""
    out: dict = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > _AUDIT_VALUE_MAX:
            out[k] = v[:_AUDIT_VALUE_MAX] + "…[truncated]"
        else:
            out[k] = v
    return out
