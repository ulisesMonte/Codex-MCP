"""Requirements enrichment — infer MCP details from natural language."""
from __future__ import annotations

import re

from langchain_core.messages import BaseMessage

from models.mcp_requirement import MCPRequirement, OutputMode, ParameterSpec, ToolSpec
from requirements.enrichment.constants import (
    _AGENT_SIDE_CLARIFICATION_RE,
    _CONCEPT_ALIASES,
    _CRUD_OPS,
    _DOMAIN_DEPS,
    _FACTORY_NAME_RE,
    _GENERIC_CONCEPTS,
    _INVALID_MCP_NAMES,
    _MICROSERVICE_LAYERS,
    _NL_SPEC_PARAM,
    _STOP_WORDS,
)
from requirements.enrichment.signals import (
    combined_user_text,
    is_affirmative,
    user_accepts_proposal,
    user_confirmed,
    user_rejects_proposal,
    user_sent_tool_correction,
)
from requirements.intent import apply_intent_to_requirement
from shared.messages import last_agent_message, last_user_message

def _ensure_tool_parameters(req: MCPRequirement) -> None:
    """Infer missing parameters so design/codegen can build real signatures."""
    text = f"{req.description} {' '.join(t.name for t in req.tools)}".lower()
    for tool in req.tools:
        if tool.parameters:
            continue
        if tool.name.endswith("_factory"):
            tool.parameters = [_NL_SPEC_PARAM.model_copy(deep=True)]
            continue
        if tool.name in _CRUD_OPS:
            from requirements.intent import resolved_intent, GenerationIntent

            if resolved_intent(req, text) == GenerationIntent.CODE_GENERATOR:
                tool.parameters = [_NL_SPEC_PARAM.model_copy(deep=True)]
                continue
            if tool.name == "read" and not tool.parameters:
                tool.parameters = [
                    ParameterSpec(
                        name="query",
                        type="str",
                        description="Id or filter expression",
                        required=False,
                        default="",
                    )
                ]
            elif tool.name == "delete" and not tool.parameters:
                tool.parameters = [
                    ParameterSpec(
                        name="id",
                        type="str",
                        description="Record identifier to delete",
                    )
                ]
            elif tool.name in ("create", "update") and not tool.parameters:
                tool.parameters = [
                    ParameterSpec(
                        name="payload",
                        type="str",
                        description=f"JSON payload for {tool.name}",
                    )
                ]
            continue
        if "google-cloud-bigquery" in req.dependencies or "bigquery" in text:
            if "connection" in tool.name or "query" in tool.name or tool.name.endswith("_connection"):
                tool.parameters = [
                    ParameterSpec(
                        name="sql",
                        type="str | None",
                        description="Optional SQL; defaults to requirement table",
                        required=False,
                        default=None,
                    ),
                    ParameterSpec(
                        name="limit",
                        type="int",
                        description="Max rows",
                        required=False,
                        default=100,
                    ),
                ]
            continue
        if any(d in req.dependencies for d in ("psycopg2-binary", "pymysql")):
            if "connection" in tool.name or "connect" in tool.name:
                tool.parameters = [
                    ParameterSpec(
                        name="database_url",
                        type="str | None",
                        description="Override DATABASE_URL env var",
                        required=False,
                        default=None,
                    )
                ]


def _ensure_microservice_factory_complete(
    req: MCPRequirement,
    text: str,
    messages: list[BaseMessage] | None = None,
) -> None:
    """Force 3 layer factory tools when user asked for controller/service/repository."""
    full_text = text
    if messages:
        full_text = f"{text}\n{combined_user_text(messages)}"

    explicit = _explicit_factory_names(full_text)
    if len(explicit) >= 3:
        count = _extract_tool_count(full_text) or len(explicit)
        req.tools = [_tool_from_name(n, full_text) for n in explicit[:count]]
        for tool in req.tools:
            if _wants_nl_code_generation(full_text) and not tool.parameters:
                tool.parameters = [_NL_SPEC_PARAM.model_copy(deep=True)]
        req.clarifications_needed = []
        if not req.description:
            req.description = (
                "MCP that generates microservice controller, service, and repository code "
                "from natural language specifications"
            )
        if req.mcp_name in ("", "microservicesfactory") or not _valid_snake(req.mcp_name):
            req.mcp_name = "microservice_factory"
        return

    if len(req.tools) >= 3 and all(t.name.endswith("_factory") for t in req.tools):
        if req.mcp_name in ("", "microservicesfactory") or not _valid_snake(req.mcp_name):
            req.mcp_name = "microservice_factory"
        return

    layers = _extract_microservice_layers(text)
    count = _extract_tool_count(text)
    wants_factory = _prefers_factory_naming(text) or bool(_FACTORY_NAME_RE.search(text))
    micro_intent = bool(re.search(r"micro\s*serv", text, re.I)) or "factory" in text.lower()

    need_three = (
        count == 3
        or len(layers) >= 3
        or (count and count >= 3)
        or bool(re.search(r"3\s+funciones?", text, re.I))
    )

    if need_three and (micro_intent or wants_factory or len(layers) >= 2):
        _set_microservice_nl_factory_tools(req, text)
        if len(req.tools) < 3:
            _set_microservice_nl_factory_tools(req, text + " controller service repository")
        req.clarifications_needed = []
        if not req.description:
            req.description = (
                "MCP that generates microservice controller, service, and repository code "
                "from natural language specifications"
            )
        if req.mcp_name in ("", "microservicesfactory") or not _valid_snake(req.mcp_name):
            req.mcp_name = "microservice_factory"
        return

    # LLM left a single wrong tool but conversation mentions 3 layers
    if len(req.tools) <= 1 and len(layers) >= 2 and micro_intent:
        _set_microservice_nl_factory_tools(req, text)


def _ensure_crud_tools_complete(
    req: MCPRequirement,
    text: str,
    messages: list[BaseMessage] | None = None,
) -> None:
    """Force create/read/update/delete when user asked for CRUD or DAO operations."""
    full_text = text
    if messages:
        full_text = f"{text}\n{combined_user_text(messages)}"

    crud_ops = _extract_crud_tools(full_text)
    if not crud_ops:
        return

    req.tools = [_crud_tool_from_op(op, full_text) for op in crud_ops]
    req.clarifications_needed = []

    if not req.description or len(req.description) < 10:
        entity = "DAO" if _mentions_dao(full_text) else "entity"
        req.description = (
            f"MCP that helps agents perform CRUD operations ({', '.join(crud_ops)}) "
            f"on {entity} records"
        )

    if not _is_valid_mcp_name(req.mcp_name):
        req.mcp_name = _infer_dao_mcp_name(full_text)


def _extract_crud_tools(text: str) -> list[str] | None:
    """Detect CRUD intent and return ordered operation names."""
    lower = text.lower()

    explicit: list[str] = []
    for op in _CRUD_OPS:
        if re.search(rf"\b{op}\b", lower):
            explicit.append(op)

    if len(explicit) >= 4:
        return list(_CRUD_OPS)

    if re.search(r"\bcrud\b", lower):
        return list(_CRUD_OPS)

    if re.search(
        r"operaciones?\s+(?:crud|del\s+dao|de\s+dao)|"
        r"crud\s+(?:del|de)\s+(?:dao|entidad)|"
        r"(?:create|crear).*(?:read|leer).*(?:update|actualiz).*(?:delete|eliminar|borrar)",
        lower,
    ):
        return list(_CRUD_OPS)

    if _mentions_dao(lower) and len(explicit) >= 2:
        return list(_CRUD_OPS)

    count = _extract_tool_count(text)
    if count == 4 and (explicit or re.search(r"crud|dao", lower)):
        return list(_CRUD_OPS)

    return None


def _mentions_dao(text: str) -> bool:
    return bool(re.search(r"\bdaos?\b", text, re.I))


def _crud_tool_from_op(op: str, text: str) -> ToolSpec:
    entity = "DAO" if _mentions_dao(text) else "record"
    descriptions = {
        "create": f"Create a new {entity}",
        "read": f"Read or query {entity} records",
        "update": f"Update an existing {entity}",
        "delete": f"Delete a {entity} record",
    }
    hints = {
        "create": f"Parse payload JSON and persist a new {entity}",
        "read": f"Query {entity} by id or filter criteria",
        "update": f"Apply partial updates to an existing {entity}",
        "delete": f"Remove {entity} by identifier",
    }
    params: list[ParameterSpec] = []
    if op == "read":
        params = [
            ParameterSpec(
                name="query",
                type="str",
                description="Id or filter expression to read records",
                required=False,
                default="",
            )
        ]
    elif op == "delete":
        params = [
            ParameterSpec(
                name="id",
                type="str",
                description=f"Identifier of the {entity} to delete",
            )
        ]
    else:
        params = [
            ParameterSpec(
                name="payload",
                type="str",
                description=f"JSON payload for {op} operation",
            )
        ]

    return ToolSpec(
        name=op,
        description=descriptions.get(op, f"Executes {op}"),
        parameters=params,
        returns_type="str",
        returns_description="Operation result as JSON/text",
        implementation_hint=hints.get(op, f"Implement {op} for {entity}"),
    )


def _infer_dao_mcp_name(text: str) -> str:
    named = _extract_named_mcp(text)
    if named and _is_valid_mcp_name(named):
        return named
    if _mentions_dao(text):
        return "dao_mcp"
    return "crud_tools"


def _extract_named_mcp(text: str) -> str:
    """Extract explicit MCP name from phrases like 'se llame X' or 'called X'."""
    patterns = [
        r"(?:se\s+llame|llamado|llamar[áa]|named|called)\s+['\"]?(\w+)['\"]?",
        r"(?:nombre|name)\s+(?:del\s+mcp|is|ser[aá]|sera)\s+['\"]?(\w+)['\"]?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return _pascal_to_snake(m.group(1))
    return ""


def _pascal_to_snake(value: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value.strip())
    s = re.sub(r"[^a-z0-9_]+", "_", s.lower())
    return s.strip("_")


def _is_valid_mcp_name(name: str) -> bool:
    return bool(_valid_snake(name) and name not in _INVALID_MCP_NAMES and len(name) >= 3)


def _apply_latest_user_tool_corrections(
    req: MCPRequirement,
    messages: list[BaseMessage],
) -> None:
    """Last user turn wins for explicit tool lists and corrections."""
    last = last_user_message(messages)
    if not last:
        return

    combined = combined_user_text(messages)
    factories = [n.lower() for n in _FACTORY_NAME_RE.findall(last)]
    explicit = _extract_proposed_tool_names(last)

    crud_ops = _extract_crud_tools(last) or _extract_crud_tools(combined)
    if crud_ops and (
        user_sent_tool_correction(last)
        or user_rejects_proposal(last)
        or len(crud_ops) >= 4
    ):
        req.tools = [_crud_tool_from_op(op, combined) for op in crud_ops]
        _infer_mcp_name(req, combined)
        req.clarifications_needed = []
        return

    # Prefer explicit *_factory names from correction message
    tool_names: list[str] = []
    seen: set[str] = set()
    for name in factories + explicit:
        key = name.lower()
        if key in seen:
            continue
        if key.endswith("_factory") or _looks_like_tool_name(key):
            seen.add(key)
            tool_names.append(key)

    if len(tool_names) >= 2:
        if _is_microservice_nl_factory(combined) or _prefers_factory_naming(combined):
            _set_microservice_nl_factory_tools(req, combined)
            # Keep order from user message when possible
            ordered = [n for n in tool_names if n.endswith("_factory")]
            if len(ordered) >= 2:
                by_name = {t.name: t for t in req.tools}
                req.tools = [by_name.get(n, _tool_from_name(n, combined)) for n in ordered]
        else:
            req.tools = [_tool_from_name(n, combined) for n in tool_names]
        _infer_mcp_name(req, combined)
        req.clarifications_needed = []
        return

    if user_sent_tool_correction(last):
        req.tools = []
        if _is_microservice_nl_factory(combined) or len(_extract_microservice_layers(combined)) >= 2:
            _set_microservice_nl_factory_tools(req, combined)
        else:
            _infer_tools_from_natural_language(req, combined, force=True)
        _infer_mcp_name(req, combined)
        req.clarifications_needed = []


def _apply_contextual_short_answer(req: MCPRequirement, messages: list[BaseMessage]) -> None:
    """Map 'sí' / 'yes' to the agent's last proposal instead of re-asking."""
    user = last_user_message(messages)
    if not user or not (is_affirmative(user) or user_accepts_proposal(user)):
        return

    agent = last_agent_message(messages) or ""
    context = combined_user_text(messages)
    combined = f"{context}\n{agent}"

    proposed = _extract_proposed_tool_names(agent) or _extract_proposed_tool_names(context)
    if not proposed:
        use_factory = _prefers_factory_naming(combined)
        concepts = _extract_tool_concepts(combined)
        proposed = [_concept_to_tool_name(c, use_factory) for c in concepts]

    if proposed:
        if _is_microservice_nl_factory(combined):
            _set_microservice_nl_factory_tools(req, combined)
        else:
            req.tools = [_tool_from_name(name, combined) for name in proposed]
        _infer_mcp_name(req, combined)
        req.clarifications_needed = []
        return

    if req.tools or req.resources:
        req.clarifications_needed = []


def _drop_answered_clarifications(req: MCPRequirement, messages: list[BaseMessage]) -> None:
    user = last_user_message(messages)
    if user_rejects_proposal(user):
        return
    if is_affirmative(user) or user_confirmed(user) or user_accepts_proposal(user):
        req.clarifications_needed = []


def _infer_tools_from_natural_language(
    req: MCPRequirement,
    text: str,
    *,
    force: bool = False,
) -> None:
    if req.tools and not force:
        return

    crud_ops = _extract_crud_tools(text)
    if crud_ops:
        req.tools = [_crud_tool_from_op(op, text) for op in crud_ops]
        return

    if _is_microservice_nl_factory(text):
        _set_microservice_nl_factory_tools(req, text)
        return

    explicit = _extract_explicit_tool_name(text)
    if explicit:
        req.tools = [_tool_from_name(explicit, text)]
        return

    proposed = _extract_proposed_tool_names(text)
    concepts = _extract_tool_concepts(text)
    use_factory = _prefers_factory_naming(text)

    if len(concepts) > 1:
        concepts = [c for c in concepts if c not in _GENERIC_CONCEPTS]

    if len(concepts) >= 2 or (concepts and not proposed):
        req.tools = [_tool_from_concept(concept, text, use_factory) for concept in concepts]
        return

    if proposed:
        req.tools = [_tool_from_name(name, text) for name in proposed]
        return

    if concepts:
        req.tools = [_tool_from_concept(concept, text, use_factory) for concept in concepts]


def _extract_proposed_tool_names(text: str) -> list[str]:
    """Pull explicit snake_case tool names from user or agent text."""
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = name.lower().replace("-", "_")
        if name in seen or name in _STOP_WORDS or not _valid_snake(name):
            return
        if not _looks_like_tool_name(name):
            return
        seen.add(name)
        names.append(name)

    for match in _FACTORY_NAME_RE.finditer(text):
        add(match.group(1))

    for match in re.finditer(r"`([a-z][a-z0-9_]*)`", text, re.I):
        add(match.group(1))

    crud_found = [op for op in _CRUD_OPS if re.search(rf"\b{op}\b", text.lower())]
    if len(crud_found) >= 2:
        for op in _CRUD_OPS:
            if op in crud_found:
                add(op)
        return names

    for match in re.finditer(r"\b([a-z][a-z0-9_]{3,})\b", text.lower()):
        add(match.group(1))

    return names


def _extract_tool_concepts(text: str) -> list[str]:
    """Extract tool purposes from natural language (any domain)."""
    concepts: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        concept = _normalize_concept(raw)
        if not concept or concept in seen or concept in _STOP_WORDS:
            return
        seen.add(concept)
        concepts.append(concept)

    segment_patterns = [
        r"(?:cada una para|otra para|y otra para|another for|one for)\s+(?:un(?:a)?\s+)?(?:generar\s+)?(\w+)",
        r"(?:tool|tools|herramienta(?:s)?)\s+(?:para|for|de)\s+(?:un(?:a)?\s+)?(?:generar\s+)?(\w+)",
        r"(?:crear|create|generar|generate)\s+(?:una?\s+)?(\w+)",
        r"(?:para|for)\s+(?:un(?:a)?\s+)?(?:generar\s+)?(\w+)",
    ]
    for pattern in segment_patterns:
        for match in re.finditer(pattern, text, re.I):
            add(match.group(1))

    concept_words = (
        r"controller|controlador|service|servicio|repository|repositorio|repositories|"
        r"connection|conexion|conexión|conexiones|query|consulta|client|cliente|"
        r"model|modelo|schema|esquema|migration|migracion|migración|auth|login|"
        r"webhook|notification|notificacion|notificación|export|import|sync|sincron"
    )
    for match in re.finditer(rf"\b({concept_words})\w*\b", text, re.I):
        add(match.group(1))

    return concepts


def _normalize_concept(raw: str) -> str:
    word = raw.strip().lower()
    if word in _CONCEPT_ALIASES:
        return _CONCEPT_ALIASES[word]
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and len(word) > 4:
        singular = word[:-1]
        if singular in _CONCEPT_ALIASES:
            return _CONCEPT_ALIASES[singular]
        return singular
    return word


def _prefers_factory_naming(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(r"_factory|\bfactory\b|scaffold|plantilla|template|generar|generate|crear micro", lower)
        or ("microservic" in lower and re.search(r"controller|service|repository|repositor", lower))
    )


def _concept_to_tool_name(concept: str, use_factory: bool) -> str:
    if use_factory:
        return f"{concept}_factory"
    if concept == "connection":
        return "create_connection"
    if concept in {"query", "consulta"}:
        return "run_query"
    return f"{concept}_tool"


def _tool_from_concept(concept: str, text: str, use_factory: bool) -> ToolSpec:
    name = _concept_to_tool_name(concept, use_factory)
    return _tool_from_name(name, text)


def _tool_from_name(name: str, text: str) -> ToolSpec:
    domain_hint = _domain_hint_for_text(text)
    label = name.replace("_", " ")
    if name.endswith("_factory"):
        base = name.removesuffix("_factory")
        description = f"Generates {base} code for the MCP use case"
        hint = f"Scaffold or generate {base} layer from inputs/templates"
    elif name.startswith("create_") or name.endswith("_connection"):
        target = _connection_target(text) or "external system"
        description = f"Creates or manages a connection to {target}"
        hint = domain_hint or f"Connection setup for {target}; use env vars for credentials"
    else:
        description = f"Executes {label}"
        hint = domain_hint or f"Implement {label} based on user intent"

    return ToolSpec(
        name=name,
        description=description,
        parameters=[],
        returns_type="str",
        returns_description="Operation result as JSON/text",
        implementation_hint=hint,
    )


def _connection_target(text: str) -> str:
    for pattern, _, label in _DOMAIN_DEPS:
        if re.search(pattern, text, re.I):
            return label.split(" via")[0]
    if re.search(r"conexi|connection|connect", text, re.I):
        return "database or external API"
    return ""


def _domain_hint_for_text(text: str) -> str:
    hints = [hint for pattern, _, hint in _DOMAIN_DEPS if re.search(pattern, text, re.I)]
    return "; ".join(hints)


def _apply_domain_context(req: MCPRequirement, text: str) -> None:
    """Add domain-specific hints and single-tool defaults (BigQuery, Postgres, etc.)."""
    lower = text.lower()
    is_connection = bool(re.search(r"conexi|connection|connect|conect", lower))

    for pattern, dep, hint in _DOMAIN_DEPS:
        if not re.search(pattern, text, re.I):
            continue

        if dep:
            deps = set(req.dependencies)
            deps.add(dep)
            req.dependencies = sorted(deps)

        if req.tools:
            for tool in req.tools:
                if not tool.implementation_hint:
                    tool.implementation_hint = hint
                if "bigquery" in pattern and (not tool.description or "?" in tool.description):
                    project = _first_match(text, r"(?:proyecto|project)\s+['\"]?(\w+)['\"]?")
                    dataset = _first_match(text, r"(?:dataset|data\s*set)\s+['\"]?(\w+)['\"]?")
                    table = _first_match(text, r"(?:tabla|table)\s+['\"]?(\w+)['\"]?")
                    if dataset and table:
                        tool.description = f"Query BigQuery table {dataset}.{table}"
                    elif project:
                        tool.description = f"Query BigQuery project {project}"
            continue

        if is_connection or "bigquery" in pattern:
            tool_name = _extract_explicit_tool_name(text)
            if not tool_name:
                if "bigquery" in pattern:
                    tool_name = "query_bigquery"
                elif is_connection:
                    tool_name = "create_connection"
                else:
                    tool_name = re.sub(r"[^a-z0-9]+", "_", pattern.split("|")[0].strip()) + "_tool"

            req.tools.append(
                ToolSpec(
                    name=tool_name,
                    description=_default_tool_description(tool_name, text, hint),
                    parameters=[],
                    returns_type="str",
                    returns_description="Operation result as JSON/text",
                    implementation_hint=hint,
                )
            )


def _default_tool_description(tool_name: str, text: str, hint: str) -> str:
    if "bigquery" in hint.lower():
        dataset = _first_match(text, r"(?:dataset|data\s*set)\s+['\"]?(\w+)['\"]?")
        table = _first_match(text, r"(?:tabla|table)\s+['\"]?(\w+)['\"]?")
        if dataset and table:
            return f"Query BigQuery table {dataset}.{table}"
    if "connection" in tool_name or "connect" in text.lower():
        target = _connection_target(text)
        return f"Create or validate connection to {target or 'external system'}"
    return f"Executes {tool_name.replace('_', ' ')}"


def _infer_tool_names(req: MCPRequirement, text: str) -> None:
    name = _extract_explicit_tool_name(text)
    if name and not req.tools:
        req.tools.append(_tool_from_name(name, text))
    elif name and req.tools and not _valid_snake(req.tools[0].name):
        req.tools[0].name = name

    if re.search(r"sin\s+par[aá]metros|no\s+parameters|without\s+parameters|no\s+tendra\s+parametros", text, re.I):
        for tool in req.tools:
            tool.parameters = []


def _extract_explicit_tool_name(text: str) -> str:
    patterns = [
        r"(?:nombre|name)\s+(?:ser[aá]|sera|is|will be)\s+['\"]?([a-z][a-z0-9_]*)['\"]?",
        r"(?:llam(?:a|ado|ar)|called)\s+['\"]?([a-z][a-z0-9_]*)['\"]?",
        r"tool\s+['\"]?([a-z][a-z0-9_]*)['\"]?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            name = m.group(1).lower()
            if name not in _STOP_WORDS and len(name) >= 3:
                return name
    return ""


def _fill_tool_defaults(req: MCPRequirement) -> None:
    for tool in req.tools:
        if tool.name:
            tool.name = tool.name.lower().replace("-", "_")
        if not tool.description and tool.name:
            tool.description = f"Executes {tool.name.replace('_', ' ')}"
        if not tool.returns_type:
            tool.returns_type = "str"
        if not tool.returns_description:
            tool.returns_description = "Operation result as JSON/text"
        for p in tool.parameters:
            if not p.description and p.name:
                p.description = p.name.replace("_", " ")
            if not p.type:
                p.type = "str"


def _infer_mcp_name(req: MCPRequirement, text: str = "") -> None:
    if _is_valid_mcp_name(req.mcp_name) and req.mcp_name not in ("microservicesfactory",):
        return

    lower = (text or "").lower()
    named = _extract_named_mcp(text)
    if named and _is_valid_mcp_name(named):
        req.mcp_name = named
        return

    if _mentions_dao(lower) and req.tools and all(t.name in _CRUD_OPS for t in req.tools):
        req.mcp_name = "dao_mcp"
        return

    if re.search(r"microservices?\s*factory|microservic", lower) and len(req.tools) >= 2:
        req.mcp_name = "microservice_factory"
        return
    explicit = _extract_explicit_tool_name(text)
    if explicit and _is_valid_mcp_name(explicit):
        req.mcp_name = explicit
        return

    if "microservic" in lower and len(req.tools) >= 2:
        req.mcp_name = "microservice_factory"
        return
    if re.search(r"conexi|connection", lower) and req.tools and "bigquery" not in lower:
        req.mcp_name = "connection_manager"
        return
    if len(req.tools) == 1 and _is_valid_mcp_name(req.tools[0].name):
        req.mcp_name = req.tools[0].name
        return
    if req.tools:
        prefix = req.tools[0].name.split("_")[0]
        if prefix and prefix not in _STOP_WORDS and _is_valid_mcp_name(f"{prefix}_tools"):
            req.mcp_name = f"{prefix}_tools"
            return
    if req.description:
        words = [
            w for w in re.findall(r"[a-z]+", req.description.lower())
            if len(w) > 3 and w not in _STOP_WORDS
        ]
        if words:
            candidate = "_".join(words[:3])[:40]
            if _is_valid_mcp_name(candidate):
                req.mcp_name = candidate


def _infer_description(req: MCPRequirement, text: str) -> None:
    if req.description:
        return
    if req.tools:
        if len(req.tools) == 1:
            req.description = req.tools[0].description
        else:
            labels = ", ".join(t.name.replace("_", " ") for t in req.tools[:3])
            req.description = f"MCP with tools: {labels}"
        return
    sentence = re.split(r"[.!?\n]", text.strip())[0].strip()
    if len(sentence) > 15:
        req.description = sentence[:200]


def _infer_dependencies(req: MCPRequirement, text: str) -> None:
    deps = set(req.dependencies)
    for pattern, dep, _ in _DOMAIN_DEPS:
        if dep and re.search(pattern, text, re.I):
            deps.add(dep)
    req.dependencies = sorted(deps)


def _infer_output_mode(req: MCPRequirement, text: str) -> None:
    lower = text.lower()
    if "deploy_http" in lower or "http api" in lower or "como api" in lower:
        req.output_mode = OutputMode.DEPLOY_HTTP
        req.transport = "http"
    elif "deploy_local" in lower or "correr local" in lower or "ejecutalo" in lower:
        req.output_mode = OutputMode.DEPLOY_LOCAL
    elif "solo codigo" in lower or "solo código" in lower or "code_only" in lower:
        req.output_mode = OutputMode.CODE_ONLY


def _filter_clarifications(notes: list[str]) -> list[str]:
    return [n for n in notes if n.strip() and not _is_agent_side_clarification(n)]


def _is_agent_side_clarification(text: str) -> bool:
    return bool(_AGENT_SIDE_CLARIFICATION_RE.search(text))


def _looks_like_tool_name(name: str) -> bool:
    if name in _STOP_WORDS or name in _INVALID_MCP_NAMES:
        return False
    if name in _CRUD_OPS:
        return True
    if "_" in name:
        return True
    return name.endswith(("factory", "connection", "manager", "tool"))


def _valid_snake(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", value or ""))


def _first_match(text: str, *patterns: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return ""


def _extract_tool_count(text: str) -> int | None:
    for pat in (
        r"(\d+)\s+(?:tools?|herramientas?)\s+distint",
        r"(?:haya|hay|with|tenga)\s+(\d+)\s+(?:tools?|herramientas?)",
        r"(\d+)\s+(?:tools?|herramientas?)",
        r"(\d+)\s+funciones?",
    ):
        m = re.search(pat, text, re.I)
        if m:
            return int(m.group(1))
    return None


def _explicit_factory_names(text: str) -> list[str]:
    """Ordered unique *_factory names explicitly mentioned by the user."""
    names: list[str] = []
    seen: set[str] = set()
    for match in _FACTORY_NAME_RE.finditer(text):
        name = match.group(1).lower()
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _extract_microservice_layers(text: str) -> list[str]:
    layer_re = re.compile(
        r"\b(controller|controlador|service|servicio|repository|repositorio|repositories)\b",
        re.I,
    )
    found: set[str] = set()
    for match in layer_re.finditer(text):
        layer = _normalize_concept(match.group(1))
        if layer in _MICROSERVICE_LAYERS:
            found.add(layer)
    return [layer for layer in _MICROSERVICE_LAYERS if layer in found]


def _wants_nl_code_generation(text: str) -> bool:
    return bool(
        re.search(
            r"lenguaje natural|natural language|prompts?|prompt de|desde texto|from text",
            text,
            re.I,
        )
    )


def _is_microservice_nl_factory(text: str) -> bool:
    layers = _extract_microservice_layers(text)
    if len(layers) < 2:
        return False
    lower = text.lower()
    has_micro = bool(re.search(r"micro\s*serv", lower))
    return has_micro and (
        len(layers) >= 3
        or _wants_nl_code_generation(text)
        or _prefers_factory_naming(text)
    )


def _set_microservice_nl_factory_tools(req: MCPRequirement, text: str) -> None:
    explicit = _explicit_factory_names(text)
    if len(explicit) >= 2:
        count = _extract_tool_count(text) or len(explicit)
        req.tools = [_tool_from_name(n, text) for n in explicit[: max(count, len(explicit))]]
        for tool in req.tools:
            if _wants_nl_code_generation(text) and not tool.parameters:
                tool.parameters = [_NL_SPEC_PARAM.model_copy(deep=True)]
        if not req.mcp_name or not _valid_snake(req.mcp_name):
            req.mcp_name = "microservice_factory"
        if not req.description:
            req.description = (
                "MCP that generates microservice controller, service, and repository code "
                "from natural language prompts"
            )
        return

    layers = _extract_microservice_layers(text) or list(_MICROSERVICE_LAYERS)
    count = _extract_tool_count(text)
    if count:
        layers = layers[:count]

    req.tools = [
        ToolSpec(
            name=f"{layer}_factory",
            description=(
                f"Generates {layer} layer Python source code from a natural language specification"
            ),
            parameters=[_NL_SPEC_PARAM.model_copy(deep=True)],
            returns_type="str",
            returns_description="Generated Python source code for the requested layer",
            implementation_hint=(
                f"Parse specification text (entity, fields, CRUD verbs) and emit complete "
                f"{layer} classes/functions — never return placeholder success strings"
            ),
        )
        for layer in layers
    ]
    if not req.mcp_name or not _valid_snake(req.mcp_name):
        req.mcp_name = "microservice_factory"
    if not req.description:
        req.description = (
            "MCP that generates microservice controller, service, and repository code "
            "from natural language prompts"
        )
