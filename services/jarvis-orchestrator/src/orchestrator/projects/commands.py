"""Commandes REPL projet : `/projects`, `/status`, `/standup`, `/idee`.

Renvoient toujours un string formaté affichable directement dans le terminal
ou dans le HUD web (le caller fait juste `print()`).

`/standup` est l'aggregateur qui combine git scan + (futur) sync Trello. Pour
l'instant on n'a pas de wrapper Trello côté Jarvis (Trello est utilisé par
Claude Code, pas par Jarvis lui-même), donc `/standup` retourne juste le
résumé git + suggestion. L'intégration Trello via MCP est dans Sprint B
Phase 4 (différée — gRPC ListTools/CallTool).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from orchestrator.projects.scanner import ProjectInfo, ProjectScanner

DEFAULT_ROOT = Path("d:/assistant_ai")


def cmd_projects(scanner: ProjectScanner | None = None) -> str:
    """Liste tous les projets sous DEFAULT_ROOT (ou root personnalisé)."""
    scanner = scanner or ProjectScanner(DEFAULT_ROOT)
    projects = scanner.scan()
    if not projects:
        return f"(aucun projet trouvé sous {scanner.root})"
    lines = [f"📁 {len(projects)} projets sous {scanner.root}", ""]
    for p in projects:
        lines.append(_format_project_line(p))
    return "\n".join(lines)


def cmd_status(name: str, *, scanner: ProjectScanner | None = None) -> str:
    """Détail d'un projet précis (nom = dossier sous DEFAULT_ROOT)."""
    scanner = scanner or ProjectScanner(DEFAULT_ROOT)
    projects = scanner.scan()
    matches = [p for p in projects if p.name.lower() == name.lower()]
    if not matches:
        names = ", ".join(p.name for p in projects) or "(aucun)"
        return f"❌ projet '{name}' introuvable. Disponibles : {names}"
    p = matches[0]
    return _format_project_detail(p)


def cmd_standup(scanner: ProjectScanner | None = None, *, days: int = 7) -> str:
    """Résumé matin : projets touchés sur les N derniers jours, dirty repos."""
    scanner = scanner or ProjectScanner(DEFAULT_ROOT)
    projects = scanner.scan()
    if not projects:
        return "(aucun projet à résumer)"
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    recent: list[ProjectInfo] = []
    dirty: list[ProjectInfo] = []
    for p in projects:
        if p.dirty_files > 0:
            dirty.append(p)
        if p.last_activity:
            try:
                ts = datetime.fromisoformat(p.last_activity)
                if ts >= cutoff:
                    recent.append(p)
            except ValueError:
                continue

    lines: list[str] = [f"☀️  Standup — {datetime.now(tz=UTC).date().isoformat()}", ""]
    lines.append(f"🔄 {len(recent)} projet(s) touché(s) les {days} derniers jours :")
    if recent:
        for p in sorted(recent, key=lambda x: x.last_activity or "", reverse=True):
            lines.append(f"   • {p.name} — {p.last_activity[:10] if p.last_activity else '?'}")
    else:
        lines.append("   (aucun)")
    lines.append("")
    lines.append(f"⚠️  {len(dirty)} repo(s) avec des modifs non commitées :")
    if dirty:
        for p in sorted(dirty, key=lambda x: x.dirty_files, reverse=True):
            branch = p.current_branch or "?"
            lines.append(f"   • {p.name} ({branch}) — {p.dirty_files} fichier(s)")
    else:
        lines.append("   (working tree propre partout)")
    return "\n".join(lines)


def cmd_idee(text: str) -> str:
    """Capture une idée. À ce stade, on l'imprime juste — la création de carte
    Trello via MCP arrivera quand le wrapping mcp-trello sera fait.
    """
    text = text.strip()
    if not text:
        return "❌ idée vide. Usage : /idee <description>"
    return (
        "💡 Idée capturée localement :\n"
        f'   "{text}"\n\n'
        "(stockage Trello via MCP : à câbler au prochain sous-sprint —\n"
        " pour l'instant, recopier sur Trello manuellement si tu veux)"
    )


# ---------------------------------------------------------------------------
# Helpers de formatage
# ---------------------------------------------------------------------------


def _format_project_line(p: ProjectInfo) -> str:
    """Une ligne par projet pour `/projects`."""
    parts: list[str] = []
    parts.append(f"📂 {p.name:<24}")
    if p.is_git_repo:
        branch = p.current_branch or "?"
        dirty = f" (✏️ {p.dirty_files})" if p.dirty_files else ""
        parts.append(f"git·{branch}{dirty}")
    else:
        parts.append("non-git")
    if p.last_activity:
        parts.append(f"dernière activité {p.last_activity[:10]}")
    parts.append(f"{_human_size(p.size_bytes_estimate)} top-niv")
    return "  ".join(parts)


def _format_project_detail(p: ProjectInfo) -> str:
    lines = [f"📂 {p.name}", f"   chemin    : {p.path}"]
    if p.is_git_repo:
        lines.append(f"   git       : oui (branche {p.current_branch or '?'})")
        lines.append(f"   modifs    : {p.dirty_files} fichier(s)")
    else:
        lines.append("   git       : non")
    lines.append(f"   dernière  : {p.last_activity or 'inconnue'}")
    lines.append(f"   taille    : {_human_size(p.size_bytes_estimate)} (top-niveau uniquement)")
    if p.notes:
        lines.append("   notes     : " + "; ".join(p.notes))
    return "\n".join(lines)


_UNITS = ("B", "KB", "MB", "GB", "TB")


def _human_size(n: int) -> str:
    f = float(n)
    for unit in _UNITS:
        if f < 1024.0:
            return f"{f:.1f} {unit}"
        f /= 1024.0
    return f"{f:.1f} PB"
