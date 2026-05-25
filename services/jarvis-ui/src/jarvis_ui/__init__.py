"""jarvis-ui : HUD web FastAPI (Iron-Man style).

Layout 3 colonnes (état système / chat / audit), accessible depuis mobile
sur LAN via `0.0.0.0:8080`. Le service est autonome — ses deps de runtime
(SystemAnswerer, AuditLogger, OllamaClient) sont lazy-importées si dispos.
"""

from jarvis_ui.app import UIDeps, create_app
from jarvis_ui.status import StatusSnapshot, collect_status

__all__ = ["StatusSnapshot", "UIDeps", "collect_status", "create_app"]
