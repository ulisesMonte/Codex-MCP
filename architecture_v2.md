# MCP Factory — Arquitectura v2 (Event Choreography)

## Contexto (v1 actual)

En v1 el flujo lo define **LangGraph**: nodos lineales + routers condicionales. Los eventos (`EventBus` + JSONL) son **observabilidad**: cada nodo llama `publish_event()` pero no decide el siguiente paso.

```
Usuario → CLI → graph.invoke() → nodos → publish_event (log)
```

Esto cumple el MVP multiagente. Para escalar (nuevos agentes, retries, composición MCP→MCP) conviene **coreografía por eventos**.

---

## Objetivo v2

Los agentes reaccionan a **eventos de dominio**. El bus es la fuente de verdad del flujo; el estado de sesión es una proyección en memoria.

```
Usuario → CLI → EventBus.publish(CreateMCPRequested)
                    ↓
              EventDispatcher
                    ↓ (handlers registrados)
         RequirementsHandler → publish(RequirementsCompleted)
                    ↓
         DesignHandler → publish(DesignCompleted)
                    ↓
         CreatorHandler → publish(CodeGenerated)
                    ↓
         ValidatorHandler → publish(ValidationPassed | ValidationRetryScheduled)
                    ↓
         DeployHandler → publish(MCPDeployed | CodeReady)
                    ↓
         RegistryHandler → publish(RegistryUpdated)
                    ↓
         CLI subscriber → SessionCompleted
```

LangGraph pasa a ser **opcional** (v2.3: wrappers finos) o se elimina cuando el dispatcher cubra todos los casos.

---

## Componentes nuevos

| Módulo | Responsabilidad |
|---|---|
| `events/dispatcher.py` | Registra `EventTypes → list[Handler]`; tras `publish`, invoca handlers |
| `orchestrator/coordinator.py` | `PipelineCoordinator`: estado de sesión + dispatch; reemplaza `graph.invoke` |
| `orchestrator/handlers/` | Un handler por etapa (`requirements.py`, `design.py`, …) |
| `orchestrator/session_state.py` | Proyección mutable (equivalente a `MCPFactoryState`) |
| `interfaces/agent.py` | Ya existe; cada handler delega en `IAgent.run()` |

### Contrato del handler

```python
class EventHandler(Protocol):
    def handles(self) -> set[str]: ...
    def handle(self, event: MCPEvent, state: SessionState, bus: EventBus) -> None: ...
```

Reglas:

- Un handler **solo** publica eventos del siguiente paso (no llama al siguiente handler directo).
- Idempotencia: si llega el mismo evento dos veces, el handler no duplica trabajo (clave: `event.sequence` + fase en state).
- Errores → `PipelineFailed` o evento específico (`DesignFailed`, etc.).

---

## Mapa evento → handler (v2.1)

| Evento entrante | Handler | Evento(s) saliente |
|---|---|---|
| `CreateMCPRequested` | — (CLI ya inició sesión) | — |
| `UserMessageReceived` | `RequirementsHandler` | `ClarificationNeeded` \| `RequirementsCompleted` |
| `RequirementsCompleted` | `DesignHandler` | `DesignCompleted` \| `DesignFailed` |
| `DesignCompleted` | `CreatorHandler` | `CodeGenerated` \| `CodeGenerationFailed` |
| `CodeGenerated` | `ValidatorHandler` | `ValidationPassed` \| `ValidationFailed` \| `ValidationRetryScheduled` |
| `ValidationRetryScheduled` | `CreatorHandler` | `CodeGenerated` (repair) |
| `ValidationPassed` | `DeployHandler` | `CodeReady` \| `MCPDeployed` \| `DeploymentFailed` |
| `CodeReady` \| `MCPDeployed` | `RegistryHandler` | `RegistryUpdated` |
| `RegistryUpdated` | — | `SessionCompleted` (CLI) |

El loop de usuario en requirements: `UserMessageReceived` hasta `RequirementsCompleted`.

---

## Estado de sesión

`SessionState` (misma información que `MCPFactoryState`):

- `session_id`, `messages`, `requirement`, `design`, `generated_mcp`
- `phase`, `validation_attempts`, `error`
- `completed_handlers: set[str]` (opcional, para idempotencia)

Persistencia:

- **Event log** (JSONL): fuente append-only (ya existe).
- **Registry** (JSON): proyección de MCPs creados (ya existe).
- Estado en RAM: reconstruible rejugando eventos (v2.5 opcional).

---

## Migración por fases

### v2.1 — Dispatcher sin romper LangGraph

- `EventBus` acepta `dispatcher: EventDispatcher | None`.
- Tras cada `publish`, el dispatcher corre handlers **solo si** `USE_EVENT_ORCHESTRATION=1`.
- LangGraph sigue siendo el camino por defecto.

### v2.2 — CLI usa coordinator

- `MCPCreateSessionRunner` llama `PipelineCoordinator.run_user_turn()` en lugar de `graph.invoke`.
- Feature flag: `ORCHESTRATION_MODE=langgraph|events` (default `langgraph` hasta estabilizar).

### v2.3 — Agentes + IAgent

- Refactor: `requirements_agent_node` → `RequirementsAgent(IAgent).run`.
- Handlers instancian agentes; tests unitarios contra `IAgent` sin LangGraph.

### v2.4 — Agent Creator (Fase 2 del producto)

- Nuevo handler: `AgentCreatorHandler` tras `RegistryUpdated` si `output_mode` incluye agente.
- Eventos: `AgentCreationStarted`, `AgentCreated`.
- Registry: campo `agent_path`.

---

## Qué NO cambia en v2

- Modelos Pydantic (`MCPRequirement`, `MCPDesign`, …)
- Ollama + fallback de modelos
- Templates Jinja2, validator determinístico, deployer
- CLI Typer y comandos existentes
- `config/paths.py` para rutas portables

---

## Criterios de aceptación v2.2

1. `ORCHESTRATION_MODE=events` completa el mismo flujo E2E que LangGraph (mismo prompt de prueba del plan).
2. `python main.py events <session_id>` muestra la misma secuencia de tipos de evento.
3. Tests de simulación en `test_events.py` pasan con dispatcher (sin LLM).
4. Fallo de validación emite `ValidationRetryScheduled` y reintenta hasta `MAX_VALIDATION_RETRIES`.

---

## Estructura de carpetas objetivo

```
orchestrator/
  coordinator.py
  session_state.py
  handlers/
    __init__.py
    requirements.py
    design.py
    creator.py
    validator.py
    deploy.py
    registry.py
events/
  dispatcher.py
  bus.py          # publish → store → subscribers → dispatcher
```

---

## Referencias en el repo actual

| v1 | Archivo |
|---|---|
| Grafo | `orchestrator/graph.py` |
| Estado | `orchestrator/state.py` |
| Publicar eventos | `orchestrator/events.py` |
| Tipos | `events/types.py` |
| Contrato agente | `interfaces/agent.py` |
| Rutas | `config/paths.py` |
