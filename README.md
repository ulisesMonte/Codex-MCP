# MCP Factory

Sistema multiagente para **generar servidores MCP** (Model Context Protocol) a partir de lenguaje natural, usando LLMs locales con [Ollama](https://ollama.com/).

---

## Requisitos

| Componente | Versión / notas |
|------------|-----------------|
| Python | 3.11+ |
| Ollama | En ejecución local (`ollama serve`) |
| Modelos | Recomendado: `llama3.1:8b` (orquestador) + `qwen2.5-coder:7b` (código) |
| GitHub token | **Opcional pero recomendado** para descargar documentación (`GITHUB_TOKEN`) |

---

## Instalación

```powershell
git clone <url-del-repo> agentes_mcp
cd agentes_mcp

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

copy .env.example .env
# Editar .env si hace falta (Ollama URL, token GitHub, etc.)
```

Verificar Ollama:

```powershell
ollama serve
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
```

---

## Documentación desde GitHub (obligatorio antes de crear MCPs)

Este repositorio **no incluye** los archivos `.md` ni docs descargados de GitHub (ver `.gitignore`). Los scouts y el RAG los necesitan en tu máquina local.

### 1. Token de GitHub (recomendado)

Sin token la API pública limita a ~60 requests/hora. Con token: ~5000/h.

1. Crear un [Personal Access Token](https://github.com/settings/tokens) (solo lectura de repos públicos).
2. Agregarlo a `.env`:

```env
GITHUB_TOKEN=ghp_tu_token_aqui
```

O exportarlo en la sesión:

```powershell
$env:GITHUB_TOKEN = "ghp_tu_token_aqui"
```

### 2. Sincronizar documentación técnica (repos curados)

Descarga README, ejemplos y código de repos como FastMCP, python-sdk, BigQuery, etc. vía **GitHub API**:

```powershell
python scripts/sync_tech_docs.py
```

Solo listar fuentes disponibles:

```powershell
python scripts/sync_tech_docs.py --list
```

Dry-run (sin descargar):

```powershell
python scripts/sync_tech_docs.py --dry-run
```

Salida: `context/docs/` (ignorado por git).

### 3. Sincronizar listas Awesome (markdown de repos enlazados)

Descarga todos los `.md` de repos referenciados en listas Awesome:

```powershell
python scripts/sync_awesome_md.py --preset tech
```

Otros presets:

```powershell
python scripts/sync_awesome_md.py --list-presets
python scripts/sync_awesome_md.py --preset mcp-ai --limit 20
```

Salida: `context/knowledge/awesome/` (ignorado por git).

### 4. Índice de descubrimiento (nombres de repos para scouts)

```powershell
python scripts/build_discovery_index.py
```

Salida: `context/discovery/ecosystem.json` (ignorado por git).

### Todo en un solo comando

```powershell
python scripts/sync_context.py --preset-tech
```

Equivale a: `sync_tech_docs` → `sync_awesome_md --preset tech` → `build_discovery_index`.

---

## Uso

### Crear un MCP (sesión interactiva)

```powershell
python main.py create
```

1. Describí en lenguaje natural qué MCP querés (tools, dominio, etc.).
2. El agente propone un resumen — revisá tools y nombre.
3. Escribí **`confirm`** cuando esté correcto (o corregí antes).
4. El pipeline corre: scouts → diseño → codegen → validación → registro.

Durante el análisis con Ollama la pantalla permanece estable (~1–2 min); al confirmar arranca el pipeline industrial (varios minutos).

### Otros comandos

| Comando | Descripción |
|---------|-------------|
| `python main.py list` | MCPs registrados |
| `python main.py show <nombre>` | Ver código generado |
| `python main.py events <session_id>` | Log de eventos de una sesión |
| `python main.py list-events` | Sesiones con logs |
| `python main.py stop <nombre>` | Detener MCP desplegado |

---

## Qué va en el repo y qué no

| Incluido en git | **No** incluido (local / generado) |
|-----------------|-------------------------------------|
| Código fuente (`agents/`, `domain/`, `services/`, …) | `.venv/`, `.env` |
| `README.md`, plantillas Jinja | `generated/mcps/` (MCPs generados) |
| `scripts/` de sync | `logs/events/` (JSONL de sesiones) |
| Tests | `registry/mcp_registry.json` |
| `.env.example` | `context/docs/` (MD descargados de GitHub) |
| | `context/knowledge/awesome/` (MD Awesome) |
| | `context/scouted/`, `context/knowledge/validated/` (runtime scouts) |

Patrones internos opcionales: podés agregar `.md` propios en `context/knowledge/` (raíz, no en `awesome/`).

---

## Configuración (`.env`)

```env
OLLAMA_BASE_URL=http://localhost:11434
MAX_VALIDATION_RETRIES=3
AGENT_THREAD_POOL_SIZE=4        # hilos para scouts, RAG y design en paralelo
ORCHESTRATION_MODE=langgraph
GITHUB_TOKEN=ghp_...          # recomendado para sync y scouts
```

Modo orquestación por eventos:

```powershell
$env:ORCHESTRATION_MODE = "events"
python main.py create
```

---

## Tests

```powershell
pytest tests/ -q
```

---

## Flujo resumido

```
Usuario → Requirements (chat + confirm)
       → 4 Scouts en paralelo (GitHub + docs locales)
       → Validación investigación → RAG feedback
       → Design (baseline ∥ RAG) → Creator (FastMCP) → Validator
       → Deploy → Registry
```

## Arquitectura del código

El proyecto está organizado por **capas** y **dominio**, no como un único paquete `agents/` monolítico.

### Capas

| Capa | Paquete | Rol |
|------|---------|-----|
| **Datos** | `models/` | Esquemas Pydantic: `MCPRequirement`, `MCPDesign`, `ScoutReport` |
| **Dominio** | `domain/` | Reglas de negocio modeladas como **clases** (POO) |
| **Servicios** | `services/` | Orquestación de casos de uso (domain + LLM + eventos) |
| **Agentes** | `agents/` | Solo nodos del pipeline (LangGraph / handlers); delgados |
| **Infra** | `cli/`, `orchestrator/`, `llm/`, `events/` | UI, grafo, Ollama, bus de eventos |

### Estructura de paquetes

```
agentes_mcp/
├── agents/                    ← Solo nodos del pipeline
│   ├── requirements/node.py
│   ├── design/node.py
│   ├── creator/node.py
│   ├── validator/node.py
│   └── scouts/                ← mcp, api, data, docs, validator
│
├── domain/                    ← Lógica de negocio (POO)
│   ├── requirements/          ← merger, intent, enricher, conversation
│   ├── codegen/               ← design_builder, code_validator
│   ├── design/                ← LlmDesignParser
│   ├── research/              ← ScoutResearchValidator
│   └── session.py             ← MCPFactorySession (facade del state)
│
├── services/                  ← Casos de uso
│   ├── requirements_service.py
│   ├── design_service.py
│   └── creator_service.py
│
├── requirements/              ← Dominio de requisitos (parseo, enrichment)
│   ├── intent.py, merge.py, response.py
│   └── enrichment/            ← signals, inference, pipeline
│
├── codegen/                   ← Generación determinista de código MCP
│   ├── router.py, core.py, tool_bodies.py, factory.py
│
├── shared/                    ← Utilidades transversales
│   ├── messages.py, signatures.py, progress.py
│   └── parallel.py            ← AgentThreadPool (hilos)
│
├── orchestrator/              ← LangGraph + handlers por eventos
├── models/, llm/, cli/, context/, deployer/, registry/, templates/
```

### Modelado orientado a objetos (POO)

Los **modelos** (`models/`) definen *qué* es cada cosa. El **dominio** (`domain/`) define *qué hace* cada cosa mediante clases con métodos:

| Clase | Responsabilidad |
|-------|-----------------|
| `RequirementMerger` | Fusiona dicts parciales del LLM → `MCPRequirement` |
| `GenerationIntentResolver` | Clasifica intent: `code_generator` / `runtime` / `integration` |
| `ConversationSignals` | Interpreta confirm, sí/no, correcciones del usuario |
| `RequirementLifecycle` | Decide `gathering` vs `complete`, mensajes de confirmación |
| `RequirementEnricher` | Inferencia NL → tools, deps, nombres |
| `DeterministicDesignBuilder` | Construye `MCPDesign` sin LLM |
| `GeneratedCodeValidator` | Valida AST + estructura FastMCP → `ValidationResult` |
| `ScoutResearchValidator` | Fusiona y valida reportes de scouts |
| `MCPFactorySession` | Vista tipada del estado del pipeline |

### Servicios de aplicación

Los nodos en `agents/*/node.py` delegan en servicios; no encadenan funciones sueltas:

| Servicio | Resultado | Uso |
|----------|-----------|-----|
| `RequirementsService` | `RequirementsTurnResult` | Turno de chat → requisito enriquecido |
| `DesignService` | `DesignResult` | Baseline determinístico + merge LLM opcional |
| `CreatorService` | `CreatorResult` | Render Jinja + reparación LLM en retry |

Ejemplo de imports:

```python
from services import RequirementsService, DesignService, CreatorService
from domain import RequirementMerger, MCPFactorySession
from requirements.enrichment import enrich_requirement   # re-export compatible
from codegen import build_design_from_requirement
```

### Paralelismo con hilos

`shared/parallel.py` expone **`AgentThreadPool`**, configurable con `AGENT_THREAD_POOL_SIZE` (default: `4`).

| Fase | Qué corre en paralelo |
|------|------------------------|
| **Scouts** | Los 4 scouts (mcp, api, data, docs) en hilos separados |
| **Design** | Baseline determinístico ∥ carga de contexto RAG |
| **Design (RAG)** | `retrieve_codegen_context` ∥ `get_similar_implementation` |
| **Design (tools)** | Si hay más de 2 tools, cada `build_tool` en un hilo |
| **Creator (repair)** | Prefetch RAG mientras se arma el prompt de reparación |

Los scouts en modo **eventos** usan el mismo pool vía `orchestrator/scout_runner.py`. LangGraph ya fan-outea scouts con `Send` en modo **langgraph**.


---

