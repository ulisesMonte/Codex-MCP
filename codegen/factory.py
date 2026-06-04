"""Deterministic code-generation bodies for microservice *_factory MCP tools."""
from __future__ import annotations

from models.mcp_design import MCPDesign, ToolImplementation
from models.mcp_requirement import MCPRequirement, ParameterSpec, ToolSpec

_FACTORY_LAYERS = ("controller", "service", "repository")


def is_microservice_factory_requirement(req: MCPRequirement) -> bool:
    if not req.tools:
        return False
    factory_tools = [t for t in req.tools if t.name.endswith("_factory")]
    if len(factory_tools) < 2:
        return False
    if "microservice" in req.mcp_name.lower():
        return True
    layers = {_layer_from_tool_name(t.name) for t in factory_tools}
    return len(layers.intersection(set(_FACTORY_LAYERS))) >= 2


def build_microservice_factory_design(req: MCPRequirement) -> MCPDesign:
    """Full MCPDesign with real NL→Python codegen bodies (no LLM stubs)."""
    tools: list[ToolImplementation] = []
    for spec in req.tools:
        layer = _layer_from_tool_name(spec.name)
        if layer not in _FACTORY_LAYERS:
            layer = "service"
        tools.append(
            ToolImplementation(
                name=spec.name,
                signature=_signature_for_tool(spec),
                return_type=spec.returns_type or "str",
                description=spec.description
                or f"Generates {layer} layer Python source from a natural language specification",
                returns_description=spec.returns_description
                or "Complete Python source code for the requested microservice layer",
                body=factory_tool_body(layer),
            )
        )

    if not tools:
        for layer in _FACTORY_LAYERS:
            tools.append(
                ToolImplementation(
                    name=f"{layer}_factory",
                    signature="specification: str",
                    return_type="str",
                    description=f"Generates {layer} layer Python source from NL specification",
                    returns_description="Complete Python source code",
                    body=factory_tool_body(layer),
                )
            )

    return MCPDesign(
        requirement=req,
        server_filename=f"{req.mcp_name}_server.py",
        imports=["import re", "import textwrap"],
        tools=tools,
        resources=[],
        has_external_calls=False,
        estimated_complexity="medium",
    )


def factory_tool_body(layer: str) -> str:
    """Indented function body shared by design fallback and deterministic design."""
    layer = layer if layer in _FACTORY_LAYERS else "service"
    return _FACTORY_BODY_TEMPLATE.format(layer=layer)


def _layer_from_tool_name(name: str) -> str:
    base = name.removesuffix("_factory").lower()
    if base.startswith("controller") or base == "controlador":
        return "controller"
    if base.startswith("service") or base.startswith("servicio"):
        return "service"
    if base.startswith("repositor"):
        return "repository"
    return base


def _signature_for_tool(spec: ToolSpec) -> str:
    if spec.parameters:
        parts = []
        for p in spec.parameters:
            if p.required:
                parts.append(f"{p.name}: {p.type or 'str'}")
            else:
                default = repr(p.default) if isinstance(p.default, str) else str(p.default)
                parts.append(f"{p.name}: {p.type or 'str'} = {default}")
        return ", ".join(parts)
    return "specification: str"


# Real multi-line Python — embedded in generated MCP server via Jinja (no JSON escaping).
_FACTORY_BODY_TEMPLATE = """\
    entity, fields, ops = _parse_microservice_spec(specification)
    entity_pascal = entity[0].upper() + entity[1:] if entity else "Entity"
    if "{layer}" == "repository":
        return _emit_repository(entity_pascal, entity, fields, ops)
    if "{layer}" == "service":
        return _emit_service(entity_pascal, entity, fields, ops)
    return _emit_controller(entity_pascal, entity, fields, ops)"""


FACTORY_MODULE_HELPERS = '''
def _parse_microservice_spec(specification: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Parse entity, fields and CRUD ops from Spanish/English NL."""
    import re

    entity = "entity"
    for pat in (
        r"(?:entity|entidad|modelo|model|tabla|table|recurso|resource)\\s*[:=]?\\s*(\\w+)",
        r"(?:for|para|de|del|la|el|un|una)\\s+(\\w+)\\s+(?:controller|service|repository|microservice)",
        r"(?:create|crear|generar|generate)\\s+(?:a|an|un|una)?\\s*(\\w+)",
        r"\\b([A-Z][a-zA-Z0-9]+)\\b",
    ):
        m = re.search(pat, specification, re.I)
        if m:
            word = m.group(1)
            if word.lower() not in {"a", "an", "un", "una", "the", "el", "la", "for", "para", "de"}:
                entity = word.lower()
                break

    fields: list[tuple[str, str]] = []
    fm = re.search(
        r"(?:fields?|campos?|atributos?|columns?|columnas?)\\s*[:=\\-]?\\s*([^\\n.]+)",
        specification,
        re.I,
    )
    if fm:
        for part in re.split(r"[,;]", fm.group(1)):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                n, t = part.split(":", 1)
                fields.append((n.strip(), t.strip()))
            elif " " in part:
                n, t = part.split(None, 1)
                fields.append((n.strip(), t.strip()))
            else:
                fields.append((part, "str"))

    if not fields:
        fields = [("id", "int"), ("name", "str")]

    ops: list[str] = []
    lower = specification.lower()
    if re.search(r"crud|create.*read.*update|crear.*leer.*actualizar", lower):
        ops = ["create", "read", "update", "delete"]
    else:
        for op, keys in (
            ("create", ("create", "crear", "insert", "alta")),
            ("read", ("read", "get", "list", "leer", "obtener", "consulta")),
            ("update", ("update", "actualizar", "modificar", "edit")),
            ("delete", ("delete", "eliminar", "borrar", "remove")),
        ):
            if any(k in lower for k in keys):
                ops.append(op)
    if not ops:
        ops = ["create", "read", "update", "delete"]
    return entity, fields, ops


def _field_lines(fields: list[tuple[str, str]], indent: str = "        ") -> list[str]:
    lines = []
    for name, typ in fields:
        py_type = {"int": "int", "str": "str", "bool": "bool", "float": "float"}.get(typ.lower(), "str")
        lines.append(f"{indent}{name}: {py_type}")
    return lines


def _emit_repository(entity_pascal: str, entity: str, fields: list[tuple[str, str]], ops: list[str]) -> str:
    import textwrap

    field_lines = _field_lines(fields)
    dataclass_fields = "\\n".join(field_lines) if field_lines else "        id: int\\n        name: str"
    methods = []
    if "create" in ops:
        methods.append(
            f"    def create(self, data: {entity_pascal}) -> {entity_pascal}:\\n"
            f"        new_id = len(self._store) + 1\\n"
            f"        item = data.model_copy(update={{'id': new_id}}) if hasattr(data, 'model_copy') else data\\n"
            f"        self._store[new_id] = item\\n"
            f"        return item"
        )
    if "read" in ops:
        methods.append(
            f"    def get(self, item_id: int) -> {entity_pascal} | None:\\n"
            f"        return self._store.get(item_id)\\n\\n"
            f"    def list(self) -> list[{entity_pascal}]:\\n"
            f"        return list(self._store.values())"
        )
    if "update" in ops:
        methods.append(
            f"    def update(self, item_id: int, data: {entity_pascal}) -> {entity_pascal} | None:\\n"
            f"        if item_id not in self._store:\\n"
            f"            return None\\n"
            f"        self._store[item_id] = data\\n"
            f"        return data"
        )
    if "delete" in ops:
        methods.append(
            f"    def delete(self, item_id: int) -> bool:\\n"
            f"        return self._store.pop(item_id, None) is not None"
        )

    body = textwrap.dedent(f"""
        from dataclasses import dataclass
        from typing import Dict

        @dataclass
        class {entity_pascal}:
        {dataclass_fields}

        class {entity_pascal}Repository:
            def __init__(self) -> None:
                self._store: Dict[int, {entity_pascal}] = {{}}

        {chr(10).join(methods)}
        """)
    return body.strip()


def _emit_service(entity_pascal: str, entity: str, fields: list[tuple[str, str]], ops: list[str]) -> str:
    import textwrap

    methods = []
    if "create" in ops:
        methods.append(
            f"    def create_{entity}(self, data: {entity_pascal}) -> {entity_pascal}:\\n"
            f"        return self._repo.create(data)"
        )
    if "read" in ops:
        methods.append(
            f"    def get_{entity}(self, item_id: int) -> {entity_pascal} | None:\\n"
            f"        return self._repo.get(item_id)\\n\\n"
            f"    def list_{entity}s(self) -> list[{entity_pascal}]:\\n"
            f"        return self._repo.list()"
        )
    if "update" in ops:
        methods.append(
            f"    def update_{entity}(self, item_id: int, data: {entity_pascal}) -> {entity_pascal} | None:\\n"
            f"        return self._repo.update(item_id, data)"
        )
    if "delete" in ops:
        methods.append(
            f"    def delete_{entity}(self, item_id: int) -> bool:\\n"
            f"        return self._repo.delete(item_id)"
        )

    body = textwrap.dedent(f"""
        from dataclasses import dataclass

        @dataclass
        class {entity_pascal}:
        {chr(10).join(_field_lines(fields)) or "        id: int\\n        name: str"}

        class {entity_pascal}Service:
            def __init__(self, repository: "{entity_pascal}Repository") -> None:
                self._repo = repository

        {chr(10).join(methods)}
        """)
    return body.strip()


def _emit_controller(entity_pascal: str, entity: str, fields: list[tuple[str, str]], ops: list[str]) -> str:
    import textwrap

    routes = []
    if "create" in ops:
        routes.append(
            f"    @router.post('/{entity}s', response_model={entity_pascal})\\n"
            f"    def create_{entity}(payload: {entity_pascal}, service: {entity_pascal}Service = Depends(get_service)):\\n"
            f"        return service.create_{entity}(payload)"
        )
    if "read" in ops:
        routes.append(
            f"    @router.get('/{entity}s/{{item_id}}', response_model={entity_pascal})\\n"
            f"    def get_{entity}(item_id: int, service: {entity_pascal}Service = Depends(get_service)):\\n"
            f"        item = service.get_{entity}(item_id)\\n"
            f"        if item is None:\\n"
            f"            raise HTTPException(status_code=404, detail='Not found')\\n"
            f"        return item\\n\\n"
            f"    @router.get('/{entity}s', response_model=list[{entity_pascal}])\\n"
            f"    def list_{entity}s(service: {entity_pascal}Service = Depends(get_service)):\\n"
            f"        return service.list_{entity}s()"
        )
    if "update" in ops:
        routes.append(
            f"    @router.put('/{entity}s/{{item_id}}', response_model={entity_pascal})\\n"
            f"    def update_{entity}(item_id: int, payload: {entity_pascal}, service: {entity_pascal}Service = Depends(get_service)):\\n"
            f"        updated = service.update_{entity}(item_id, payload)\\n"
            f"        if updated is None:\\n"
            f"            raise HTTPException(status_code=404, detail='Not found')\\n"
            f"        return updated"
        )
    if "delete" in ops:
        routes.append(
            f"    @router.delete('/{entity}s/{{item_id}}')\\n"
            f"    def delete_{entity}(item_id: int, service: {entity_pascal}Service = Depends(get_service)):\\n"
            f"        if not service.delete_{entity}(item_id):\\n"
            f"            raise HTTPException(status_code=404, detail='Not found')\\n"
            f"        return {{'deleted': True}}"
        )

    body = textwrap.dedent(f"""
        from dataclasses import dataclass
        from fastapi import APIRouter, Depends, HTTPException

        @dataclass
        class {entity_pascal}:
        {chr(10).join(_field_lines(fields)) or "        id: int\\n        name: str"}

        router = APIRouter(prefix='/{entity}s', tags=['{entity_pascal}'])

        def get_service() -> {entity_pascal}Service:
            raise NotImplementedError("Wire {entity_pascal}Service in app startup")

        {chr(10).join(routes)}
        """)
    return body.strip()
'''
