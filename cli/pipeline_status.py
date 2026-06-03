"""Map pipeline events to human-readable status lines for the CLI."""
from __future__ import annotations

from events.model import MCPEvent
from events.types import EventTypes


def status_for_event(event: MCPEvent) -> str | None:
    """Return a short status string for the chat panel, or None to keep current."""
    payload = event.payload or {}
    et = event.type

    if et == EventTypes.REQUIREMENTS_STARTED:
        return "Analizando requirements (Ollama)…"
    if et == EventTypes.REQUIREMENTS_COMPLETED:
        return "Requirements OK — iniciando relevamiento (4 scouts)…"
    if et == EventTypes.CLARIFICATION_NEEDED:
        return "Tu turno — el agente necesita una aclaración."

    if et == EventTypes.SCOUT_STARTED:
        profile = payload.get("profile", "?")
        return f"Scout [{profile}] — relevando repos y código…"
    if et == EventTypes.SCOUT_COMPLETED:
        profile = payload.get("profile", "?")
        files = payload.get("files", 0)
        return f"Scout [{profile}] listo ({files} archivos)…"
    if et == EventTypes.SCOUT_VALIDATION_STARTED:
        return "Validando investigación de scouts…"
    if et == EventTypes.SCOUT_VALIDATION_COMPLETED:
        return "Investigación OK — diseñando MCP (Ollama)…"

    if et == EventTypes.DESIGN_STARTED:
        return "Design agent — resolviendo arquitectura (Ollama)…"
    if et == EventTypes.DESIGN_COMPLETED:
        return "Design listo — generando código…"
    if et == EventTypes.DESIGN_FAILED:
        return "Error en design — revisá events/log."

    if et == EventTypes.CODE_GENERATION_STARTED:
        attempt = payload.get("attempt", 0)
        suffix = f" (retry {attempt})" if attempt else ""
        return f"Creator agent — generando Python{suffix}…"
    if et == EventTypes.CODE_GENERATED:
        return "Código generado — validando…"

    if et == EventTypes.VALIDATION_STARTED:
        return "Validator — chequeando AST y estructura…"
    if et == EventTypes.VALIDATION_PASSED:
        return "Validación OK — deploy…"
    if et == EventTypes.VALIDATION_RETRY_SCHEDULED:
        return "Validación falló — reparando código…"

    if et == EventTypes.DEPLOYMENT_STARTED:
        return "Deployer — preparando salida…"
    if et == EventTypes.CODE_READY:
        return "Código listo — actualizando registry…"
    if et == EventTypes.MCP_DEPLOYED:
        return "MCP desplegado — actualizando registry…"

    if et == EventTypes.REGISTRY_UPDATED:
        return "Registry actualizado — finalizando…"

    if et in (EventTypes.PIPELINE_FAILED, EventTypes.SESSION_FAILED, EventTypes.DEPLOYMENT_FAILED):
        return f"Error: {event.message[:80]}"

    return None
