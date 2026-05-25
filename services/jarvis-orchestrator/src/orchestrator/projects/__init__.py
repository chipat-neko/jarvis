"""Module `orchestrator.projects` : gestion multi-projets sur le disque.

Scanne `d:/assistant_ai/*/` pour produire un état synthétique de chaque projet
(git status, dernière activité, taille). Sert pour :
- la commande `/projects` qui liste tous les projets en cours
- la commande `/status [projet]` qui zoom sur un projet précis
- la commande `/standup` qui résume Trello + git d'un coup
- la commande `/idee <texte>` qui crée une carte Trello dans Propositions

Le scanner est volontairement minimaliste : pas de RAG, pas d'embeddings,
juste `git` + `os.stat`. Ça suffit pour la session de matin de Noah.
"""

from orchestrator.projects.scanner import ProjectInfo, ProjectScanner

__all__ = ["ProjectInfo", "ProjectScanner"]
