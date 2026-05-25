"""Module Q/R structuré pour Jarvis.

Trois answerers spécialisés :
- FilesAnswerer : recherche / lecture fichiers locaux (avec whitelist PathWhitelist)
- GitAnswerer : git status / log / branches du repo courant
- SystemAnswerer : état système (CPU, RAM, GPU, processus, Ollama up?)

Cf recherche 103 (`d:/assistant_ai/recherche/103-jarvis-qr-pour-noah/`) pour
le design et les 7 familles de questions.

Pour l'instant, ces answerers sont appelés manuellement (heuristique simple
sur le prompt). Le tool calling natif via MCP arrivera au Sprint B.
"""

from orchestrator.q_and_a.files_answerer import FilesAnswer, FilesAnswerer
from orchestrator.q_and_a.git_answerer import GitAnswer, GitAnswerer
from orchestrator.q_and_a.router import Intent, IntentMatch, IntentRouter
from orchestrator.q_and_a.system_answerer import SystemAnswer, SystemAnswerer

__all__ = [
    "FilesAnswer",
    "FilesAnswerer",
    "GitAnswer",
    "GitAnswerer",
    "Intent",
    "IntentMatch",
    "IntentRouter",
    "SystemAnswer",
    "SystemAnswerer",
]
