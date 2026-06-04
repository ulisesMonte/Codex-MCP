# MCP Factory 

Sistema multiagente que genera servidores **Model Context Protocol (MCP)** a partir de lenguaje natural. Describí qué querés crear y el sistema diseña, programa, valida y despliega un servidor MCP listo para usar.

---

# ¿Qué es esto?

MCP Factory es un pipeline multiagente de nivel productivo desarrollado en Python.

Simplemente describís en lenguaje natural qué tipo de servidor MCP necesitás, qué herramientas debe exponer y qué funcionalidades debe ofrecer.

El sistema se encarga de:

* Investigar documentación relevante
* Diseñar la arquitectura
* Generar el código utilizando FastMCP
* Validar la implementación
* Registrar y desplegar el MCP generado

## Ejemplo

> Necesito un MCP que lea y escriba archivos dentro de un directorio controlado, liste los archivos disponibles y permita buscar texto dentro de ellos.

↓

**2-3 minutos después**

```text
✅ file_manager_mcp generado y registrado

Herramientas:
- list_files
- read_file
- write_file
- search_in_files

Archivo:
generated/mcps/file_manager_mcp_20250601_143022.py
```

---

# Arquitectura

```text
Usuario (lenguaje natural)
          ↓

Requirements Agent
(Chat interactivo + confirmación)

          ↓

┌─────────────────────────────────────┐
│     4 Scout Agents (paralelo)       │
│                                     │
│   mcp · api · data · docs           │
│                                     │
│ GitHub API + documentación local    │
└─────────────┬───────────────────────┘
              ↓

 Validación de investigación
 + feedback RAG

              ↓

┌─────────────────────────────┐
│ Diseño (paralelo)           │
│                             │
│ Determinístico ∥ Basado RAG │
│                             │
│ Contexto ChromaDB           │
└─────────────┬───────────────┘
              ↓

      Creator Agent
(FastMCP + plantillas Jinja2)

              ↓

     Validator Agent
 (AST Check + revisión LLM)

              ↓

   Deploy + Registry
(MCP registrado y listo para usar)
```

---

# Modelos utilizados

Se utilizan dos LLMs especializados:

## llama3.1:8b

Responsable de:

* Orquestación
* Levantamiento de requisitos
* Razonamiento de diseño
* Toma de decisiones

## qwen2.5-coder:7b

Responsable de:

* Generación de código
* Corrección de errores
* Reparación automática

---

# Stack Tecnológico

* Python
* LangGraph
* Ollama
* FastMCP
* ChromaDB
* GitHub API
* Jinja2
* Pydantic

---

# Arquitectura del Código

El proyecto está organizado por capas y evita una estructura monolítica basada únicamente en agentes.

```text
agentes_mcp/
│
├── agents/
│   ├── requirements/node.py
│   ├── design/node.py
│   ├── creator/node.py
│   ├── validator/node.py
│   └── scouts/
│       ├── mcp
│       ├── api
│       ├── data
│       ├── docs
│       └── validator
│
├── domain/
│   ├── requirements/
│   │   ├── merger
│   │   ├── intent
│   │   ├── enricher
│   │   └── conversation
│   │
│   ├── codegen/
│   │   ├── design_builder
│   │   └── code_validator
│   │
│   ├── design/
│   │   └── LlmDesignParser
│   │
│   ├── research/
│   │   └── ScoutResearchValidator
│   │
│   └── session.py
│       └── MCPFactorySession
│
├── services/
│   ├── requirements_service.py
│   ├── design_service.py
│   └── creator_service.py
│
├── codegen/
│
├── shared/
│   ├── AgentThreadPool
│   ├── progress
│   └── signatures
│
└── orchestrator/
    ├── LangGraph
    └── event_handlers
```

## Decisiones de diseño

### models/

Define qué son las cosas.

Ejemplos:

* Requisitos
* Diseños
* Herramientas
* Eventos

Utiliza esquemas Pydantic.

### domain/

Define qué hacen las cosas.

Contiene:

* Lógica de negocio
* Reglas
* Casos de uso internos

Implementado con clases orientadas a objetos.

### agents/

Nodos del pipeline.

Su responsabilidad es:

* Recibir estado
* Delegar a servicios
* Devolver resultados

No contienen lógica de negocio.

### Paralelismo

Se implementa mediante:

```python
AgentThreadPool
```

con cantidad de hilos configurable.

---

# Ejecución Paralela

| Fase             | Ejecución en paralelo                                      |
| ---------------- | ---------------------------------------------------------- |
| Scouts           | 4 agentes Scout en hilos independientes                    |
| Diseño           | Baseline determinístico + carga de contexto RAG            |
| Diseño (RAG)     | retrieve_codegen_context + get_similar_implementation      |
| Diseño (tools)   | Cada herramienta se diseña en paralelo si hay más de 2     |
| Creator (repair) | Prefetch RAG mientras se construye el prompt de reparación |

---

# Primeros Pasos

## Requisitos

* Python 3.11+
* Ollama ejecutándose localmente

## Instalación

```bash
git clone https://github.com/ulisesMonte/Codex-MCP.git agentes_mcp

cd agentes_mcp

python -m venv .venv

source .venv/bin/activate
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```bash
pip install -e ".[dev]"
```

Copiar variables de entorno:

```bash
cp .env.example .env
```

---

# Descargar los modelos

```bash
ollama serve

ollama pull llama3.1:8b

ollama pull qwen2.5-coder:7b
```

---

# Sincronizar documentación

Obligatorio antes del primer uso.

```bash
python scripts/sync_context.py --preset-tech
```

Este comando descarga:

* Documentación MCP
* Ejemplos FastMCP
* Índices del ecosistema MCP desde GitHub

### Recomendación

Agregar un token de GitHub en `.env`:

```env
GITHUB_TOKEN=ghp_xxxxxxxxx
```

Límites:

* Sin token: 60 requests/hora
* Con token: 5000 requests/hora

---

# Crear tu primer MCP

```bash
python main.py create
```

Describí en lenguaje natural qué querés construir.

El sistema propondrá:

* Nombre del MCP
* Herramientas
* Diseño inicial

Revisalo y escribí:

```text
confirm
```

para ejecutar el pipeline completo.

---

# Comandos CLI

| Comando                              | Descripción               |
| ------------------------------------ | ------------------------- |
| `python main.py create`              | Crear un nuevo MCP        |
| `python main.py list`                | Listar MCPs registrados   |
| `python main.py show <nombre>`       | Mostrar código generado   |
| `python main.py events <session_id>` | Ver eventos de una sesión |
| `python main.py list-events`         | Ver todas las sesiones    |
| `python main.py stop <nombre>`       | Detener un MCP desplegado |

---

# Configuración

```env
OLLAMA_BASE_URL=http://localhost:11434

MAX_VALIDATION_RETRIES=3

AGENT_THREAD_POOL_SIZE=4

ORCHESTRATION_MODE=langgraph
# alternativas:
# events

GITHUB_TOKEN=ghp_xxxxxxxxx
```

---

# Tests

```bash
pytest tests/ -q
```

---

# Qué se versiona y qué permanece local

## Se incluye en Git

```text
agents/
domain/
services/
codegen/
shared/
orchestrator/

README.md

templates Jinja

scripts/

tests/

registry/mcp_registry.json

.env.example
```

## Solo local

```text
.venv/

.env

generated/mcps/

logs/events/

context/docs/

context/knowledge/
```

---

MCP Factory permite pasar de una descripción funcional a un servidor MCP completamente operativo mediante un pipeline multiagente especializado en investigación, diseño, generación de código, validación y despliegue automatizado.
