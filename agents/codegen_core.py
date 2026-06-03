"""Shared NL→Python codegen helpers and tool bodies for any requirement."""
from __future__ import annotations

from pathlib import Path

from models.mcp_requirement import MCPRequirement, ToolSpec

_CRUD_OPS = frozenset({"create", "read", "update", "delete"})

_HELPERS_PATH = Path(__file__).with_name("codegen_helpers_runtime.py")
CODEGEN_MODULE_HELPERS = _HELPERS_PATH.read_text(encoding="utf-8")
RUNTIME_MODULE_HELPERS = "def _runtime_store(entity: str = 'default') -> dict:\n    if not hasattr(_runtime_store, '_stores'):\n        _runtime_store._stores = {}\n    if entity not in _runtime_store._stores:\n        _runtime_store._stores[entity] = {}\n    return _runtime_store._stores[entity]\n"


def is_code_generator_requirement(req: MCPRequirement) -> bool:
    from agents.requirement_intent import GenerationIntent, resolved_intent

    text = f"{req.description} {' '.join(t.name for t in req.tools)}"
    return resolved_intent(req, text) == GenerationIntent.CODE_GENERATOR


def code_generator_tool_body(tool: ToolSpec, req: MCPRequirement) -> str:
    """Return indented body for a code-generation tool."""
    name = tool.name.lower()
    if name in _CRUD_OPS:
        return _CRUD_CODEGEN_BODY.format(op=name)
    if name.endswith("_factory"):
        target = name.removesuffix("_factory").replace("_", " ")
        return _FACTORY_STYLE_BODY.format(target=target)
    label = name.replace("_", " ")
    return _GENERIC_CODEGEN_BODY.format(label=label)


_CRUD_CODEGEN_BODY = """\
    entity, fields, _ops = _parse_nl_spec(specification)
    entity_pascal = entity[0].upper() + entity[1:] if entity else "Entity"
    return _emit_crud_method(entity_pascal, entity, fields, "{op}")"""


_FACTORY_STYLE_BODY = """\
    entity, fields, _ops = _parse_nl_spec(specification)
    entity_pascal = entity[0].upper() + entity[1:] if entity else "Entity"
    return _emit_component(entity_pascal, entity, fields, "{target}")"""


_GENERIC_CODEGEN_BODY = """\
    entity, fields, _ops = _parse_nl_spec(specification)
    entity_pascal = entity[0].upper() + entity[1:] if entity else "Entity"
    return _emit_component(entity_pascal, entity, fields, "{label}")"""


def runtime_crud_body(op: str, entity: str = "entity") -> str:
    if op == "create":
        return f"""    import json as _json
    try:
        data = _json.loads(payload)
    except Exception:
        data = {{"raw": payload}}
    store = _runtime_store("{entity}")
    new_id = str(len(store) + 1)
    data["id"] = new_id
    store[new_id] = data
    return _json.dumps({{"tool": "create", "created": data, "id": new_id}}, default=str)"""

    if op == "read":
        return f"""    store = _runtime_store("{entity}")
    if query:
        items = [v for k, v in store.items() if query in str(k) or query in str(v)]
    else:
        items = list(store.values())
    return json.dumps({{"tool": "read", "query": query, "count": len(items), "items": items}}, default=str)"""

    if op == "update":
        return f"""    import json as _json
    try:
        data = _json.loads(payload)
    except Exception:
        data = {{"raw": payload}}
    record_id = str(data.get("id", ""))
    store = _runtime_store("{entity}")
    if record_id not in store:
        return _json.dumps({{"tool": "update", "error": "not_found", "id": record_id}})
    store[record_id] = {{**store[record_id], **data}}
    return _json.dumps({{"tool": "update", "updated": store[record_id]}}, default=str)"""

    if op == "delete":
        return f"""    store = _runtime_store("{entity}")
    removed = store.pop(record_id, None)
    return json.dumps({{"tool": "delete", "deleted": removed is not None, "id": record_id}}, default=str)"""

    return ""
