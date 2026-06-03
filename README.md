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
| Código fuente (`agents/`, `cli/`, …) | `.venv/`, `.env` |
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
       → 4 Scouts (GitHub + docs locales)
       → Validación investigación → RAG feedback
       → Design → Creator (FastMCP) → Validator
       → Deploy → Registry
```

Arquitectura detallada: `architecture_v2.md`.

---

## Referencias

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [Ollama](https://ollama.com/)
