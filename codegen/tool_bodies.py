"""Domain-aware tool body generation for any MCP requirement."""
from __future__ import annotations

import re

from codegen.core import (
    CODEGEN_MODULE_HELPERS,
    RUNTIME_MODULE_HELPERS,
    code_generator_tool_body,
    is_code_generator_requirement,
    runtime_crud_body,
)
from requirements.intent import GenerationIntent, resolved_intent
from shared.signatures import params_to_signature
from models.mcp_requirement import MCPRequirement, ParameterSpec, ToolSpec

_CRUD_OPS = frozenset({"create", "read", "update", "delete"})


def tool_domain(tool: ToolSpec, req: MCPRequirement) -> str:
    text = _context_text(tool, req)
    intent = resolved_intent(req, text)

    if tool.name.endswith("_factory"):
        if _is_microservice_layer_factory(tool.name):
            return "microservice_layer"
        return "nl_factory"

    if re.search(r"plsql|pl/sql|oracle", text):
        return "plsql"

    if intent == GenerationIntent.CODE_GENERATOR:
        return "code_generator"

    if "google-cloud-bigquery" in req.dependencies or "bigquery" in text:
        return "bigquery"
    if any(d in req.dependencies for d in ("psycopg2-binary", "pymysql", "pymongo")):
        return "database"
    if "sqlite" in text and ("database" in text or "connection" in tool.name):
        return "database"
    if "httpx" in req.dependencies or re.search(r"\bhttp\b|rest api|api externa", text):
        return "http"
    if re.search(r"pandas|dataframe|csv", text):
        return "pandas"
    if intent == GenerationIntent.RUNTIME and tool.name in _CRUD_OPS:
        return "runtime_crud"
    return "generic"


def _context_text(tool: ToolSpec, req: MCPRequirement) -> str:
    return " ".join(
        [
            req.mcp_name,
            req.description,
            tool.name,
            tool.description,
            tool.implementation_hint,
            " ".join(req.dependencies),
        ]
    ).lower()


def _is_microservice_layer_factory(name: str) -> bool:
    base = name.removesuffix("_factory").lower().rstrip("s")
    return base in {"controller", "controlador", "service", "servicio", "repository", "repositorio"}


def signature_for_tool(tool: ToolSpec, domain: str) -> str:
    if domain == "code_generator":
        if tool.parameters and _has_specification_param(tool):
            return params_to_signature(tool.parameters)
        return "specification: str"
    if tool.parameters:
        return params_to_signature(tool.parameters)
    if domain == "bigquery":
        return "sql: str | None = None, limit: int = 100"
    if domain == "database":
        if "connection" in tool.name or "connect" in tool.name:
            return "database_url: str | None = None"
        return "sql: str, params: tuple | None = None"
    if domain == "http":
        return "path: str = '', method: str = 'GET', body: str | None = None"
    if domain in ("nl_factory", "microservice_layer", "plsql"):
        return "specification: str"
    if domain == "runtime_crud":
        return _runtime_crud_signature(tool.name)
    if tool.name in _CRUD_OPS:
        return _runtime_crud_signature(tool.name)
    if tool.name.startswith(("get_", "fetch_", "read_", "query_", "list_", "search_")):
        return "query: str = ''"
    if tool.name.startswith(("create_", "add_", "insert_", "update_", "delete_")):
        return "payload: str"
    return ""


def _runtime_crud_signature(name: str) -> str:
    if name == "read":
        return "query: str = ''"
    if name == "delete":
        return "record_id: str"
    if name in ("create", "update"):
        return "payload: str"
    return ""


def _has_specification_param(tool: ToolSpec) -> bool:
    return any(p.name == "specification" for p in tool.parameters)


def build_tool_body(tool: ToolSpec, req: MCPRequirement, domain: str | None = None) -> str:
    domain = domain or tool_domain(tool, req)
    if domain == "microservice_layer":
        from codegen.factory import factory_tool_body

        layer = tool.name.removesuffix("_factory").lower().rstrip("s")
        if layer.startswith("controlador"):
            layer = "controller"
        elif layer.startswith("servicio"):
            layer = "service"
        elif layer.startswith("repositor"):
            layer = "repository"
        return factory_tool_body(layer)

    builders = {
        "bigquery": _body_bigquery,
        "database": _body_database,
        "http": _body_http,
        "plsql": _body_plsql,
        "nl_factory": _body_nl_factory,
        "code_generator": _body_code_generator,
        "runtime_crud": _body_runtime_crud,
        "pandas": _body_pandas,
        "generic": _body_generic,
    }
    return builders.get(domain, _body_generic)(tool, req)


def get_module_helpers(req: MCPRequirement) -> str:
    """Helpers injected into generated MCP server templates."""
    from codegen.factory import FACTORY_MODULE_HELPERS, is_microservice_factory_requirement

    if is_microservice_factory_requirement(req):
        return FACTORY_MODULE_HELPERS.strip()
    if is_code_generator_requirement(req):
        return CODEGEN_MODULE_HELPERS.strip()
    if any(t.name.endswith("_factory") for t in req.tools):
        return CODEGEN_MODULE_HELPERS.strip()
    text = f"{req.description} {' '.join(t.name for t in req.tools)}"
    if resolved_intent(req, text) == GenerationIntent.RUNTIME and any(
        t.name in _CRUD_OPS for t in req.tools
    ):
        return RUNTIME_MODULE_HELPERS.strip()
    return ""


def imports_for_requirement(req: MCPRequirement) -> list[str]:
    imports = ["import os", "import json"]
    deps = set(req.dependencies)
    text = (req.description + " " + " ".join(t.name for t in req.tools)).lower()

    if is_code_generator_requirement(req):
        imports.extend(["import re", "import textwrap"])

    if "google-cloud-bigquery" in deps or "bigquery" in text:
        imports.append("from google.cloud import bigquery")
    if "psycopg2-binary" in deps or "postgres" in text:
        imports.append("import psycopg2")
    if "pymysql" in deps or "mysql" in text:
        imports.append("import pymysql")
    if "pymongo" in deps or "mongo" in text:
        imports.append("from pymongo import MongoClient")
    if "httpx" in deps:
        imports.append("import httpx")
    if "pandas" in deps:
        imports.append("import pandas as pd")

    seen: set[str] = set()
    out: list[str] = []
    for imp in imports:
        if imp not in seen:
            seen.add(imp)
            out.append(imp)
    return out


def _body_code_generator(tool: ToolSpec, req: MCPRequirement) -> str:
    return code_generator_tool_body(tool, req)


def _body_runtime_crud(tool: ToolSpec, req: MCPRequirement) -> str:
    entity = _default_entity(req)
    return runtime_crud_body(tool.name, entity)


def _default_entity(req: MCPRequirement) -> str:
    if re.search(r"\bdaos?\b", req.description, re.I):
        return "dao"
    words = re.findall(r"[a-z]+", req.mcp_name)
    return words[0] if words else "entity"


def _body_bigquery(tool: ToolSpec, req: MCPRequirement) -> str:
    project, dataset, table = _extract_bq_refs(req, tool)
    if project:
        default_table = f"`{project}.{dataset}.{table}`"
    elif dataset:
        default_table = f"`{dataset}.{table}`"
    else:
        default_table = f"`{table}`"

    return f"""    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise ValueError("Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON path")
    client = bigquery.Client.from_service_account_json(credentials_path)
    query = sql or "SELECT * FROM {default_table} LIMIT {{limit}}"
    job = client.query(query)
    rows = [dict(row) for row in job.result()]
    return json.dumps({{"query": query, "row_count": len(rows), "rows": rows}}, default=str)"""


def _body_database(tool: ToolSpec, req: MCPRequirement) -> str:
    text = (tool.name + tool.description + req.description).lower()
    if "connection" in tool.name or "connect" in text:
        if "mongo" in text or "pymongo" in req.dependencies:
            return """    uri = database_url or os.getenv("MONGODB_URI")
    if not uri:
        raise ValueError("Set MONGODB_URI or pass database_url")
    client = MongoClient(uri)
    client.admin.command("ping")
    return json.dumps({"status": "connected", "uri_host": uri.split("@")[-1]})"""
        if "mysql" in text or "pymysql" in req.dependencies:
            return """    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("Set DATABASE_URL or pass database_url")
    conn = pymysql.connect(host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "postgres"))
    conn.close()
    return json.dumps({"status": "connected"})"""
        return """    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("Set DATABASE_URL or pass database_url")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.fetchone()
    cur.close()
    conn.close()
    return json.dumps({"status": "connected"})"""

    return """    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("Set DATABASE_URL")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return json.dumps({"sql": sql, "rows": rows}, default=str)"""


def _body_http(tool: ToolSpec, req: MCPRequirement) -> str:
    return """    base = os.getenv("API_BASE_URL", "").rstrip("/")
    if not base:
        raise ValueError("Set API_BASE_URL")
    url = f"{base}/{path.lstrip('/')}" if path else base
    headers = {}
    token = os.getenv("API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=30.0) as client:
        response = client.request(method.upper(), url, headers=headers, content=body)
        response.raise_for_status()
        try:
            data = response.json()
        except Exception:
            data = response.text
    return json.dumps({"url": url, "status": response.status_code, "data": data}, default=str)"""


def _body_plsql(tool: ToolSpec, req: MCPRequirement) -> str:
    return """    import re
    name = "generated_proc"
    m = re.search(r"(?:procedure|procedimiento|proc|funcion|function)\\s+(\\w+)", specification, re.I)
    if m:
        name = m.group(1)
    entity = "item"
    em = re.search(r"(?:for|para|table|tabla|entity|entidad)\\s+(\\w+)", specification, re.I)
    if em:
        entity = em.group(1)
    body_lines = [
        f"CREATE OR REPLACE PROCEDURE {name} AS",
        "BEGIN",
        f"  -- Generated from: {specification[:120]!r}",
        f"  NULL; -- entity: {entity}",
        "  COMMIT;",
        "END;",
        "/",
    ]
    return "\\n".join(body_lines)"""


def _body_nl_factory(tool: ToolSpec, req: MCPRequirement) -> str:
    target = tool.name.removesuffix("_factory").replace("_", " ")
    return f"""    entity, fields, _ops = _parse_nl_spec(specification)
    entity_pascal = entity[0].upper() + entity[1:] if entity else "Entity"
    return _emit_component(entity_pascal, entity, fields, "{target}")"""


def _body_pandas(tool: ToolSpec, req: MCPRequirement) -> str:
    return """    path = os.getenv("DATA_PATH", query or "data.csv")
    if not path:
        raise ValueError("Set DATA_PATH or pass query as file path")
    df = pd.read_csv(path)
    summary = {
        "path": path,
        "rows": len(df),
        "columns": list(df.columns),
        "preview": df.head(5).to_dict(orient="records"),
    }
    return json.dumps(summary, default=str)"""


def _body_generic(tool: ToolSpec, req: MCPRequirement) -> str:
    name = tool.name.lower()
    hint = tool.implementation_hint or tool.description or req.description

    verb_body = _body_by_verb(name, tool, hint)
    if verb_body:
        return verb_body

    if tool.parameters:
        return _body_from_parameters(tool, hint)

    return f"""    # {hint}
    return json.dumps({{"tool": "{tool.name}", "status": "ok", "message": "{tool.description[:80]}"}}, default=str)"""


def _body_by_verb(name: str, tool: ToolSpec, hint: str) -> str:
    if name == "read" or name.startswith(("get_", "fetch_", "read_", "query_", "list_", "search_")):
        return f"""    # {hint}
    data = {{"tool": "{tool.name}", "query": query, "items": []}}
    return json.dumps(data, default=str)"""

    if name == "create" or name.startswith(("create_", "add_", "insert_")):
        return f"""    # {hint}
    import json as _json
    try:
        parsed = _json.loads(payload)
    except Exception:
        parsed = {{"raw": payload}}
    return _json.dumps({{"tool": "{tool.name}", "created": parsed}}, default=str)"""

    if name == "update" or name.startswith(("update_", "patch_", "modify_")):
        return f"""    # {hint}
    import json as _json
    try:
        parsed = _json.loads(payload)
    except Exception:
        parsed = {{"raw": payload}}
    return _json.dumps({{"tool": "{tool.name}", "updated": parsed}}, default=str)"""

    if name == "delete" or name.startswith(("delete_", "remove_")):
        param = "record_id" if "record_id" in (tool.parameters and [p.name for p in tool.parameters] or []) else "payload"
        if param == "record_id":
            return f"""    # {hint}
    return json.dumps({{"tool": "{tool.name}", "deleted": record_id}}, default=str)"""
        return f"""    # {hint}
    return json.dumps({{"tool": "{tool.name}", "deleted": payload}}, default=str)"""

    if name.startswith(("validate_", "check_", "test_")):
        return f"""    # {hint}
    ok = bool(payload)
    return json.dumps({{"tool": "{tool.name}", "valid": ok, "input": payload}}, default=str)"""

    return ""


def _body_from_parameters(tool: ToolSpec, hint: str) -> str:
    """Build meaningful bodies from parameter names — never bare echo stubs."""
    names = [p.name for p in tool.parameters]
    name_set = set(names)

    if "specification" in name_set:
        return f"""    # {hint}
    entity, fields, _ops = _parse_nl_spec(specification)
    entity_pascal = entity[0].upper() + entity[1:] if entity else "Entity"
    return _emit_component(entity_pascal, entity, fields, "{tool.name.replace("_", " ")}")"""

    if "sql" in name_set:
        return f"""    # {hint}
    raise NotImplementedError("Wire SQL execution for {tool.name}")"""

    if "payload" in name_set:
        return f"""    # {hint}
    import json as _json
    try:
        parsed = _json.loads(payload)
    except Exception:
        parsed = {{"raw": payload}}
    return _json.dumps({{"tool": "{tool.name}", "result": parsed}}, default=str)"""

    if "query" in name_set:
        return f"""    # {hint}
    return json.dumps({{"tool": "{tool.name}", "query": query, "items": []}}, default=str)"""

    if "message" in name_set:
        return f"""    # {hint}
    return json.dumps({{"tool": "{tool.name}", "echo": message}}, default=str)"""

    if len(names) == 1:
        var = names[0]
        return f"""    # {hint}
    return json.dumps({{"tool": "{tool.name}", "result": {var}}}, default=str)"""

    result_build = ", ".join(f'"{n}": {n}' for n in names)
    return f"""    # {hint}
    return json.dumps({{"tool": "{tool.name}", "result": {{{result_build}}}}}, default=str)"""


def _extract_bq_refs(req: MCPRequirement, tool: ToolSpec) -> tuple[str, str, str]:
    text = " ".join([req.description, tool.description, tool.implementation_hint])
    project = _first(text, r"(?:proyecto|project)\s+['\"]?([\w-]+)['\"]?")
    dataset = _first(text, r"(?:dataset|data\s*set)\s+['\"]?([\w-]+)['\"]?")
    table = _first(text, r"(?:tabla|table)\s+['\"]?([\w-]+)['\"]?")
    if not table:
        table = _first(text, r"[\w-]+\.([\w-]+)")
    return project or "", dataset or "dataset", table or "table"


def _first(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.I)
    return m.group(1) if m else ""
