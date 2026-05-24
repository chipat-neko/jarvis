# Architecture Decision Records (ADR)

> Trace des décisions structurantes prises sur Jarvis. Chaque ADR explique le **pourquoi** d'un choix, pas seulement le quoi.

Quand on revient sur le projet dans 6 mois et qu'on se demande « pourquoi diable on a fait X et pas Y ? », la réponse est ici.

---

## Convention

- **Numérotation séquentielle** : `0001-`, `0002-`, ... (jamais de gaps, jamais de renumbering)
- **Format de nom** : `NNNN-titre-en-kebab-case.md`
- **Format de contenu** : voir [`_template.md`](_template.md)
- **Langue** : français (cohérent avec le reste du projet)
- **Immutabilité** : un ADR accepté ne se modifie pas. Si on change d'avis, on crée un **nouvel ADR** qui supersede l'ancien (`Statut: Superseded by ADR-XXXX`). L'historique reste lisible.

## Quand créer un ADR

Crée un ADR pour toute décision qui :
- ✅ Affecte l'architecture globale (choix de langage, framework, pattern, communication)
- ✅ Engage le projet sur plusieurs sprints (pas une feature ponctuelle)
- ✅ Présente des trade-offs non-évidents que tu voudrais réexpliquer plus tard
- ✅ Pourrait être remise en question dans le futur

**Pas besoin d'ADR pour** : choix de nom de variable, formatage, dépendance mineure, fix de bug, refactor d'un module.

## Workflow

1. Brouillon dans une PR avec statut `Proposed`
2. Discussion / questions / clarifications
3. Quand validé → merge avec statut `Accepted` et date
4. Si jamais on revient dessus → nouvel ADR avec statut de l'ancien passé à `Superseded by ADR-XXXX`

## Index des ADR

| ID | Titre | Statut | Date |
|---|---|---|---|
| [ADR-0001](0001-microservices-python-rust.md) | Architecture microservices Python + Rust | Accepted | 2026-05-24 |

---

## Pour aller plus loin

- [adr.github.io](https://adr.github.io/) — site de référence sur les ADRs
- Format inspiré de [Michael Nygard's template](https://github.com/joelparkerhenderson/architecture-decision-record/blob/main/locales/en/templates/decision-record-template-by-michael-nygard/index.md)
- Trello board Jarvis : décisions discutées dans la colonne **Explication** puis archivées en ADR ici

🔗 Mémoire Claude associée : `~/.claude/projects/d--assistant-ai/memory/project_jarvis_architecture.md`
