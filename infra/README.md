# infra/

Infrastructure-as-code pour Jarvis : Docker Compose, systemd units, configs Prometheus/Grafana.

## Contenu (a venir)

- `docker-compose.yml` : Home Assistant, Prometheus, Grafana
- `systemd/` : units pour demarrer les services Jarvis au boot (Linux/WSL)
- `prometheus/prometheus.yml` : scrape configs pour les microservices
- `grafana/dashboards/` : dashboards JSON (voice-pipeline, llm-routing, system)

Cf cartes Trello "Setup observability stack" et "CI multi-services GitHub Actions".
