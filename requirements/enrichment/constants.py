"""Regex patterns and domain constants for requirement enrichment."""
from __future__ import annotations

import re

from models.mcp_requirement import ParameterSpec

# User only needs to confirm — agents handle credentials, types, etc.
_AGENT_SIDE_CLARIFICATION_RE = re.compile(
    r"client\s*id|credential|api\s*key|secret|autenticaci[oó]n|authentication|"
    r"tipo de retorno|return type|snake_case|pip package|dependenc",
    re.IGNORECASE,
)

_CONFIRM_RE = re.compile(
    r"^(confirm|confirmar)\.?$",
    re.IGNORECASE,
)

# Common typos when user means "confirm"
_CONFIRM_TYPO_RE = re.compile(
    r"^conf[io]?r?m\.?$",
    re.IGNORECASE,
)

_AFFIRMATIVE_RE = re.compile(
    r"^(s[ií]|yes|yep|ok|okay|dale|correcto|est[aá]\s+bien|de\s+acuerdo|exacto|perfecto)\.?$",
    re.IGNORECASE,
)

_AFFIRMATIVE_START_RE = re.compile(
    r"^(?:s[ií]|yes|yep|ok|okay|dale|correcto|est[aá]\s+bien|de\s+acuerdo|exacto|perfecto)\b",
    re.IGNORECASE,
)

_CONFIRMATION_INTENT_RE = re.compile(
    r"(?:"
    r"eso\s+es\s+(?:lo\s+que\s+)?quiero|"
    r"as[ií]\s+es|"
    r"exactamente|"
    r"generalo|gener[aá]lo|"
    r"hacelo|hac[eé]lo|"
    r"adelante|"
    r"de\s+acuerdo|"
    r"est[aá]\s+bien|"
    r"correcto|"
    r"perfecto|"
    r"dale|"
    r"quiero\s+eso|"
    r"^ok\b"
    r")",
    re.IGNORECASE,
)

_AGENT_ASKED_CONFIRM_RE = re.compile(
    r"confirm|confirmar|¿es\s+correcto|es\s+correcto|propongo|¿confirm",
    re.IGNORECASE,
)

_USER_TOOL_CORRECTION_RE = re.compile(
    r"debe\s+tener|son\s+\d+\s+tools?|uno\s+para\s+cada|"
    r"no\s+es\s+una\s+sola|(?:^|\s)\d+\s+tools?|tres\s+tools?|cuatro\s+tools?|"
    r"osea|o\s+sea|me\s+refiero|corrijo|quiero\s+\d+|"
    r"create|read|update|delete|crud",
    re.I,
)

_USER_REJECT_RE = re.compile(
    r"^(?:no(?:pe)?|nah)\b|"
    r"no\s+(?:es\s+)?(?:correcto|as[ií]|exacto|v[aá]lido|lo\s+que\s+quiero)|"
    r"(?:est[aá]|es)\s+(?:mal|incorrecto|equivocado|err[oó]neo)|"
    r"no\s+(?:quiero|sirve|est[aá]\s+bien)|"
    r"\b(?:incorrecto|equivocado|mal\s+as[ií])\b|"
    r"\b(?:cambiar|corregir|faltan?)\b",
    re.I,
)

_CRUD_OPS = ("create", "read", "update", "delete")

_INVALID_MCP_NAMES = {
    "del", "de", "la", "el", "los", "las", "un", "una", "y", "o", "en", "con",
    "para", "por", "que", "mcp", "tool", "tools", "dao", "crud", "operacion",
    "operaciones", "funcion", "funciones", "parte", "microservicesfactory",
}

_FACTORY_NAME_RE = re.compile(r"\b([a-z][a-z0-9_]*_factory)\b", re.I)

_GENERIC_CONCEPTS = {
    "microservicio", "microservice", "mcp", "codigo", "code", "tool", "tools",
    "logica", "logic", "microservciio", "microservciios", "propmt", "prompts",
}

_MICROSERVICE_LAYERS = ("controller", "service", "repository")

_NL_SPEC_PARAM = ParameterSpec(
    name="specification",
    type="str",
    description="Natural language description of what to generate (entity, fields, CRUD, framework)",
)

_STOP_WORDS = {
    "que", "una", "uno", "the", "para", "con", "mcp", "tool", "tools", "bigquery",
    "sera", "ser", "haga", "eso", "como", "cada", "otra", "distintas", "generar",
    "crear", "need", "want", "necesito", "quiero", "herramienta",
    "herramientas", "nombre", "name", "nombres", "descriptivo", "descriptivos",
    "microservicio", "microservicios", "microservice", "microservices",
    "del", "de", "la", "el", "los", "las", "y", "o", "en", "por", "parte",
    "operacion", "operaciones", "funcion", "funciones", "ultimo", "ultima",
    "debe", "tener", "correcto", "incorrecto", "solo", "sola", "agente", "agentes",
    "ayude", "ayudar", "sirva", "servir", "partir", "daos", "crud",
}

_CONCEPT_ALIASES = {
    "servicio": "service",
    "servicios": "service",
    "repositorio": "repository",
    "repositorios": "repository",
    "repositories": "repository",
    "conexion": "connection",
    "conexión": "connection",
    "conexiones": "connection",
    "connections": "connection",
    "controlador": "controller",
    "controladores": "controller",
}

_DOMAIN_DEPS: list[tuple[str, str, str]] = [
    (r"bigquery|big query", "google-cloud-bigquery", "BigQuery via GOOGLE_APPLICATION_CREDENTIALS"),
    (r"postgres(?:ql)?", "psycopg2-binary", "PostgreSQL via DATABASE_URL env var"),
    (r"mysql|mariadb", "pymysql", "MySQL via DATABASE_URL env var"),
    (r"mongodb|mongo\b", "pymongo", "MongoDB via MONGODB_URI env var"),
    (r"redis", "redis", "Redis via REDIS_URL env var"),
    (r"sqlite", "", "SQLite file path via SQLITE_PATH env var"),
    (r"httpx|http api|rest api", "httpx", "HTTP client; credentials via env vars"),
    (r"pandas", "pandas", "Data processing with pandas"),
]
