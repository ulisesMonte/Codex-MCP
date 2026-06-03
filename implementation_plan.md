# MCP Factory — MVP Plan (Actualizado)

## Decisiones Finales

| Pregunta | Respuesta |
|---|---|
| LLM | **Local via Ollama** — setup heterogéneo (ver abajo) |
| Código base | Repo portable (`agentes_mcp/`); rutas vía `config/paths.py` |
| Output mode | **CODE_ONLY** (devuelve el código) + **DEPLOY_LOCAL** (lanza el server) |
| MCP capabilities | `@mcp.tool()` + `@mcp.resource()` + HTTP endpoints |
| Scope MVP | **Solo MCP Factory** — Agent Creator es Fase 2 |

---

## LLM Local — Setup Heterogéneo con Ollama

Se usan **dos modelos especializados** corriendo en Ollama:

| Rol | Modelo | VRAM | Por qué |
|---|---|---|---|
| **Orchestrator** | `llama3.3:70b` | ~40GB | Mejor razonamiento, planning, JSON structured output |
| **Code Generator** | `qwen2.5-coder:32b` | ~20GB | SOTA en code gen local, menos errores de sintaxis |

> [!IMPORTANT]
> Si no tenés suficiente VRAM para ambos, hay alternativas:
> - VRAM limitada (≤16GB): usar `qwen2.5-coder:14b` para todo
> - VRAM media (24GB): `llama3.1:8b` para orquestación + `qwen2.5-coder:14b` para código
> - El sistema detecta automáticamente qué modelos están disponibles en Ollama

**Interface**: Ollama API en `http://localhost:11434` — LangChain tiene integración nativa (`ChatOllama`).

---

## Output Modes del Sistema

El sistema soporta 3 modos de output:

```
OutputMode.CODE_ONLY     → Devuelve el código Python del MCP como string/archivo
OutputMode.DEPLOY_LOCAL  → Lanza el MCP server como subprocess local
OutputMode.DEPLOY_HTTP   → Lanza el MCP server en modo HTTP (SSE transport)
```

El usuario elige el modo como parte del flujo de requerimientos.

---

## Arquitectura MVP

```
Usuario (prompts en lenguaje natural)
          │
          ▼
┌──────────────────────────────┐
│      CLI (Typer)             │  main.py — loop conversacional
│      + Session Manager       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│    Orchestrator (LangGraph)  │  Llama 3.3 — coordinación
│       StateGraph             │
└───────┬──────────────────────┘
        │
   ┌────┴──────────────────────────┐
   ▼                               ▼
┌──────────────┐         ┌────────────────────┐
│ Requirements │         │   MCP Designer     │
│    Agent     │         │   + Code Creator   │  Qwen2.5-Coder
│ (llama3.3)   │         │   (qwen2.5-coder)  │
└──────────────┘         └────────┬───────────┘
   Itera hasta                    │
   completitud                    ▼
                         ┌────────────────────┐
                         │  Validator Agent   │
                         │  (ast.parse +      │
                         │   import check)    │
                         └────────┬───────────┘
                                  │
                    ┌─────────────┼──────────────┐
                    ▼             ▼               ▼
             CODE_ONLY      DEPLOY_LOCAL    DEPLOY_HTTP
             (archivo .py)  (subprocess)   (HTTP/SSE)
                    │             │               │
                    └─────────────┴───────────────┘
                                  │
                                  ▼
                         Registry Update
                         (mcp_registry.json)
```

---

## Estructura de Archivos (MVP)

```
d:\agentes_mcp\
│
├── main.py                        # Entry point: CLI + session loop
│
├── orchestrator/
│   ├── __init__.py
│   ├── graph.py                   # LangGraph StateGraph
│   ├── state.py                   # MCPFactoryState
│   └── router.py                  # Routing condicional entre nodos
│
├── agents/
│   ├── __init__.py
│   ├── requirements_agent.py      # Relevamiento iterativo sin ambigüedades
│   ├── mcp_design_agent.py        # Diseño técnico del MCP
│   ├── mcp_creator_agent.py       # Generación de código (Qwen2.5-Coder)
│   └── validator_agent.py         # Validación + retry loop
│
├── models/
│   ├── __init__.py
│   ├── mcp_requirement.py         # MCPRequirement, ToolSpec, ResourceSpec, ParameterSpec
│   └── mcp_design.py              # MCPDesign, GeneratedMCP, OutputMode
│
├── templates/
│   ├── mcp_server_stdio.py.j2     # Template: MCP con stdio transport
│   ├── mcp_server_http.py.j2      # Template: MCP con HTTP/SSE transport
│   └── mcp_resource.py.j2         # Template: @mcp.resource() snippet
│
├── deployer/
│   ├── __init__.py
│   ├── local_deployer.py          # Lanza server como subprocess
│   └── process_manager.py         # Gestiona procesos corriendo (start/stop/status)
│
├── registry/
│   ├── __init__.py
│   ├── registry_manager.py        # CRUD sobre mcp_registry.json
│   └── mcp_registry.json          # Registro de MCPs creados
│
├── generated/
│   └── mcps/                      # MCPs generados van acá
│
├── llm/
│   ├── __init__.py
│   └── ollama_client.py           # Wrapper de ChatOllama con fallback de modelos
│
├── tests/
│   ├── test_requirements_agent.py
│   ├── test_mcp_creator_agent.py
│   ├── test_validator_agent.py
│   └── fixtures/
│       └── sample_requirements.py # Fixtures de requerimientos de prueba
│
├── .env                           # OLLAMA_BASE_URL, MODEL_ORCHESTRATOR, MODEL_CODER
├── pyproject.toml
└── README.md
```

---

## Modelos de Datos

### `models/mcp_requirement.py`

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Literal

class OutputMode(str, Enum):
    CODE_ONLY = "code_only"       # Devuelve el código Python
    DEPLOY_LOCAL = "deploy_local"  # Lanza como subprocess local (stdio)
    DEPLOY_HTTP = "deploy_http"    # Lanza como servidor HTTP/SSE

class ParameterSpec(BaseModel):
    name: str
    type: str               # "str", "int", "bool", "list[str]", "dict", etc.
    description: str
    required: bool = True
    default: Any = None

class ToolSpec(BaseModel):
    name: str               # snake_case
    description: str
    parameters: list[ParameterSpec]
    returns_type: str       # tipo Python del retorno
    returns_description: str
    implementation_hint: str = ""  # pista sobre qué debe hacer internamente

class ResourceSpec(BaseModel):
    uri_template: str       # ej: "data://products/{product_id}"
    name: str
    description: str
    returns_type: Literal["str", "bytes"] = "str"
    mime_type: str = "text/plain"

class MCPRequirement(BaseModel):
    mcp_name: str
    description: str
    tools: list[ToolSpec] = []
    resources: list[ResourceSpec] = []
    transport: Literal["stdio", "http"] = "stdio"
    dependencies: list[str] = []     # pip packages necesarios
    output_mode: OutputMode = OutputMode.CODE_ONLY
    port: int = 8000                 # solo relevante si transport=http
    is_complete: bool = False        # True cuando no hay más ambigüedades
    clarifications_needed: list[str] = []  # preguntas pendientes
```

### `models/mcp_design.py`

```python
class MCPDesign(BaseModel):
    requirement: MCPRequirement
    server_filename: str
    imports: list[str]
    tool_implementations: list[dict]   # {"name": str, "code": str}
    resource_implementations: list[dict]
    has_external_calls: bool = False
    estimated_complexity: Literal["simple", "medium", "complex"] = "simple"

class GeneratedMCP(BaseModel):
    design: MCPDesign
    code: str                  # código Python completo del server
    server_path: str           # ruta absoluta del archivo generado
    status: Literal["generated", "deployed", "error"] = "generated"
    deployment_pid: int | None = None  # si está corriendo como proceso
    deployment_url: str | None = None  # si es HTTP
    validation_passed: bool = False
    validation_errors: list[str] = []
```

---

## Flujo Detallado por Nodo

### Nodo 1: `requirements_agent`

**Modelo**: Llama 3.3 (razonamiento + preguntas)

**System Prompt** (resumen):
> Eres un analista técnico especializado en MCP (Model Context Protocol). Tu trabajo es extraer requerimientos completos y sin ambigüedad para generar un MCP server con FastMCP. Nunca asumas nada. Pregunta hasta tener claro: nombre del MCP, qué tools expone (con parámetros y tipos), qué resources expone, si necesita APIs externas, qué tipo de transport (stdio/http), y cómo quiere el output (código o deployado).

**Criterios de completitud** (checklist interno del agente):
```
□ mcp_name definido (snake_case, descriptivo)
□ Al menos 1 tool O 1 resource definido
□ Cada tool: nombre, descripción, parámetros tipados, tipo de retorno
□ Cada resource: URI template, descripción, tipo de retorno
□ Transport definido (stdio o http)
□ Dependencies externas identificadas
□ Output mode definido (code_only / deploy_local / deploy_http)
□ Si deploy_http: puerto definido
```

**Comportamiento**:
- En cada turno genera un JSON interno con el estado del checklist
- Si hay ítems sin marcar, genera preguntas específicas para el usuario
- Cuando todo está marcado, setea `is_complete = True` y muestra resumen para confirmación

---

### Nodo 2: `mcp_design_agent`

**Modelo**: Qwen2.5-Coder (diseño técnico)

**Input**: `MCPRequirement` completo

**Output**: `MCPDesign` con:
- Lista de imports necesarios
- Firma exacta de cada tool (con type hints completos)
- Firma exacta de cada resource
- Identificación de si se necesitan stubs externos (APIs, DB, etc.)

---

### Nodo 3: `mcp_creator_agent`

**Modelo**: Qwen2.5-Coder

**Input**: `MCPDesign` + template Jinja2

**Proceso**:
1. Renderiza template base con Jinja2
2. Pasa el resultado + diseño al LLM para completar la lógica de cada tool/resource
3. Escribe el archivo en `generated/mcps/{mcp_name}_server.py`

**Template base (`mcp_server_stdio.py.j2`)**:
```jinja
# Generated by MCP Factory
# {{ timestamp }} | Model: {{ model_version }}
# MCP: {{ mcp_name }}

from fastmcp import FastMCP
{% for imp in imports %}
{{ imp }}
{% endfor %}

mcp = FastMCP("{{ mcp_name }}")

{% for tool in tools %}
@mcp.tool()
def {{ tool.name }}({{ tool.signature }}) -> {{ tool.return_type }}:
    """{{ tool.description }}
    
    Returns:
        {{ tool.returns_description }}
    """
    # TODO: Implementar
    {{ tool.placeholder_impl }}

{% endfor %}
{% for resource in resources %}
@mcp.resource("{{ resource.uri_template }}")
def {{ resource.name }}({% if resource.has_params %}{{ resource.params }}{% endif %}) -> {{ resource.return_type }}:
    """{{ resource.description }}"""
    # TODO: Implementar
    {{ resource.placeholder_impl }}

{% endfor %}
if __name__ == "__main__":
    mcp.run()
```

---

### Nodo 4: `validator_agent`

**Sin LLM** — validación determinística:

```python
def validate_mcp(code: str, dependencies: list[str]) -> ValidationResult:
    # 1. Sintaxis Python
    ast.parse(code)
    
    # 2. Tiene import de fastmcp
    assert "from fastmcp import FastMCP" in code
    
    # 3. Tiene al menos 1 decorator
    assert "@mcp.tool()" in code or "@mcp.resource(" in code
    
    # 4. Tiene if __name__ == "__main__"
    assert 'if __name__ == "__main__"' in code
    
    # 5. Chequea imports disponibles (solo los que no son stdlib/fastmcp)
    for dep in dependencies:
        importlib.util.find_spec(dep)  # no falla si no está instalado, solo avisa
```

**Retry loop**: Si falla, vuelve al `mcp_creator_agent` con el error como feedback. Máximo 3 intentos.

---

### Nodo 5: `deployer` (condicional)

**Solo se ejecuta si `output_mode != CODE_ONLY`**:

```python
# DEPLOY_LOCAL (stdio)
process = subprocess.Popen(
    ["python", server_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
# Guarda PID en registry para poder terminar el proceso después

# DEPLOY_HTTP
process = subprocess.Popen(
    ["python", server_path, "--transport", "http", "--port", str(port)]
)
# URL: http://localhost:{port}
```

---

### Nodo 6: `registry_updater`

Actualiza `mcp_registry.json`:
```json
{
  "version": "1.0",
  "mcps": [
    {
      "id": "uuid-v4",
      "name": "ecommerce_tools",
      "description": "...",
      "server_path": "generated/mcps/ecommerce_tools_server.py",
      "transport": "stdio",
      "output_mode": "deploy_local",
      "tools": ["buscar_producto", "agregar_al_carrito"],
      "resources": ["data://products/{id}"],
      "dependencies": ["httpx"],
      "status": "active",
      "deployment_pid": 12345,
      "deployment_url": null,
      "created_at": "2026-05-29T...",
      "validation_passed": true
    }
  ]
}
```

---

## `llm/ollama_client.py` — Fallback Automático

```python
ORCHESTRATOR_MODELS = [
    "llama3.3:70b",
    "llama3.1:70b", 
    "llama3.1:8b",      # fallback mínimo
]

CODER_MODELS = [
    "qwen2.5-coder:32b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",  # fallback mínimo
]

def get_available_model(candidates: list[str]) -> str:
    """Detecta qué modelos están disponibles en Ollama y elige el mejor."""
    available = ollama.list()  # llama a http://localhost:11434/api/tags
    for model in candidates:
        if model in available:
            return model
    raise RuntimeError(f"Ninguno de los modelos disponibles: {candidates}")
```

---

## Fases de Implementación (MVP) — Estado real (Jun 2026)

> Checklist actualizado según el código en repo. Pendientes menores al final.

### Fase 1 — Setup
- [x] Plan aprobado
- [x] `pyproject.toml` + dependencias (hatchling / pip install -e .)
- [x] Estructura de directorios (+ `cli/`, `events/`, `config/`)
- [x] `.env.example` y `ollama_client.py` con fallback
- [x] Modelos Pydantic completos
- [x] `config/paths.py` — rutas relativas al root del proyecto

### Fase 2 — Requirements Agent
- [x] `requirements_agent.py` con system prompt + checklist
- [x] Loop conversacional: itera hasta `is_complete = True`
- [x] `main.py` + `cli/session_runner.py` (Typer)

### Fase 3 — LangGraph StateGraph
- [x] `state.py` con `MCPFactoryState`
- [x] `graph.py` con nodos y edges
- [x] `router.py` con lógica condicional
- [x] MemorySaver + interrupt en requirements (`wait_for_user`)

### Fase 4 — MCP Design + Creator
- [x] Templates Jinja2 (stdio y http)
- [x] `mcp_design_agent.py`
- [x] `mcp_creator_agent.py` con retry feedback
- [ ] Test E2E con Ollama real (manual; depende de modelos locales)

### Fase 5 — Validator + Deployer
- [x] `validator_agent.py` con validación determinística
- [x] `local_deployer.py` + `process_manager.py`
- [x] Tests unitarios de validator

### Fase 6 — Registry + CLI completa
- [x] `registry_manager.py`
- [x] `mcp_registry.json` inicial
- [x] CLI: `create`, `list`, `stop`, `status`, `show`, `events`, `list-events`

### Fase 7 — Polish
- [x] Tests: `test_events`, `test_validator_agent`, `test_mcp_requirement`, `test_session_runner`
- [x] README con ejemplos
- [ ] Demo documentada con 3 MCPs distintos generados
- [ ] Recrear `.venv` en cada máquina (`python -m venv .venv`)

---

## Dependencias (`pyproject.toml`)

```toml
[project]
name = "mcp-factory"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-ollama>=0.2.0",    # ChatOllama
    "fastmcp>=2.0.0",
    "jinja2>=3.1.0",
    "pydantic>=2.0.0",
    "typer>=0.12.0",
    "python-dotenv>=1.0.0",
    "ollama>=0.3.0",              # python client oficial de Ollama
    "rich>=13.0.0",               # output bonito en CLI
    "uuid>=1.30",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

---

## Prerequisitos del Sistema

Antes de correr el proyecto:
1. **Instalar Ollama**: https://ollama.com/download
2. **Descargar modelos**:
   ```bash
   ollama pull llama3.3:70b         # orquestador (si hay VRAM)
   ollama pull qwen2.5-coder:32b    # generador de código
   # Alternativa liviana:
   ollama pull qwen2.5-coder:14b
   ollama pull llama3.1:8b
   ```
3. **Verificar**: `ollama list` debe mostrar los modelos

---

## Verificación del MVP

### Test End-to-End
Prompt de entrada: *"Quiero un MCP que tenga una tool para calcular el precio final de un producto aplicando descuentos y otra para verificar si hay stock"*

**Resultado esperado**:
1. El sistema pregunta: nombre del MCP, parámetros exactos (¿qué tipo de descuento? ¿porcentaje o monto fijo?), tipo de retorno, si necesita BD o API externa
2. Una vez relevado todo: genera `precio_tools_server.py`
3. Valida que el código Python es correcto
4. Registra en `mcp_registry.json`
5. Output: código del MCP + opción de deployarlo

### Comandos de verificación
```bash
# Correr el sistema
uv run python main.py create

# Ver MCPs registrados
uv run python main.py list

# Ver estado de un MCP deployado
uv run python main.py status precio_tools

# Detener un MCP
uv run python main.py stop precio_tools

# Verificar que el MCP generado es Python válido
uv run python -c "import ast; ast.parse(open('generated/mcps/precio_tools_server.py').read()); print('OK')"
```

---

## Fase 2 (Post-MVP): Agent Creator

Una vez que el MVP esté estable, se agrega:
- `agents/agent_creator_agent.py` — genera un agente que usa el MCP creado
- `templates/agent.py.j2` — template del agente
- Nuevo nodo en el grafo: `agent_creator_agent`
- Nuevo campo en registry: `"agent_path"`

---

## Actualizacion: Arquitectura Event-Driven Local

Se agrega una capa event-driven incremental sin reemplazar LangGraph:

```
CLI
  -> EventBus
  -> JsonlEventStore logs/events/{session_id}.jsonl
  -> LangGraph actual instrumentado
  -> Rich Live View
```

### Decisiones

| Decision | Resultado |
|---|---|
| Backend interno | Sin endpoints; solo eventos locales |
| Orquestacion | Se mantiene LangGraph en esta etapa |
| Event store | JSONL append-only |
| Observabilidad | Log propio; no OpenTelemetry |
| Registry | Proyeccion final consultable, no log principal |

### Archivos agregados

```
events/
  __init__.py
  model.py      # MCPEvent
  types.py      # EventTypes
  store.py      # JsonlEventStore
  bus.py        # EventBus
  runtime.py    # registry en memoria por session_id
  view.py       # tablas Rich para live/history
```

### Eventos implementados

- [x] CLI: `CreateMCPRequested`, `UserMessageReceived`, `SessionCompleted`, `SessionFailed`
- [x] Requirements: `RequirementsStarted`, `RequirementUpdated`, `ClarificationNeeded`, `RequirementsCompleted`
- [x] Design: `DesignStarted`, `DesignCompleted`, `DesignFailed`
- [x] Creator: `CodeGenerationStarted`, `CodeGenerated`, `CodeRepairStarted`, `CodeGenerationFailed`
- [x] Validator: `ValidationStarted`, `ValidationPassed`, `ValidationFailed`, `ValidationRetryScheduled`
- [x] Deployer: `DeploymentStarted`, `CodeReady`, `MCPDeployed`, `DeploymentFailed`
- [x] Registry: `RegistryUpdateStarted`, `RegistryUpdated`
- [x] Error handler: `PipelineFailed`

### CLI de eventos

```powershell
python main.py create
python main.py events <session_id>
python main.py list-events
```

### Checklist de pruebas

- [x] `MCPEvent` serializa/deserializa en JSONL
- [x] `JsonlEventStore` mantiene orden por `sequence`
- [x] `EventBus.publish` persiste y notifica subscribers
- [x] Payloads con modelos Pydantic se convierten a JSON seguro
- [x] Simulacion de flujo exitoso termina en `RegistryUpdated` + `SessionCompleted`
- [x] Simulacion de validacion fallida emite `ValidationRetryScheduled`

### Refactor SOLID aplicado

- [x] SRP: `main.py` queda como adaptador Typer; el loop interactivo vive en `cli/session_runner.py`.
- [x] SRP: re-adjuntar procesos desde registry vive en `cli/processes.py`.
- [x] SRP: sanitizacion JSON-safe de payloads vive en `events/serialization.py`.
- [x] DIP: `EventBus` depende del protocolo `EventStore`, no del store JSONL concreto.
- [x] ISP: `events/protocols.py` expone contratos chicos (`EventStore`, `EventSubscriber`).
- [x] OCP: se puede agregar otro store de eventos sin modificar `EventBus`.

---

## Arquitectura v2 — Event Choreography (próximo)

Ver diseño detallado en **[architecture_v2.md](./architecture_v2.md)**.

Resumen: mantener agentes especializados, pero reemplazar edges fijos de LangGraph por **handlers que reaccionan a eventos de dominio** (`RequirementsCompleted` → design, etc.). LangGraph queda como adaptador opcional o se retira por fases.

| Etapa | Objetivo |
|---|---|
| v2.1 | `EventDispatcher` + handlers por `EventTypes` |
| v2.2 | `PipelineCoordinator` sustituye `graph.invoke` en CLI |
| v2.3 | Agentes implementan `IAgent`; nodos LangGraph = thin wrappers |
| v2.4 | Fase 2: `agent_creator_agent` + eventos de composición |
