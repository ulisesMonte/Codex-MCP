# Microservice layer code generation from natural language

## Architecture
Typical Python microservice layers:
1. **Controller** — HTTP routes, request/response DTOs, delegates to service.
2. **Service** — business logic, orchestration, validation.
3. **Repository** — data access (SQL/ORM), CRUD, query building.

## Factory tool pattern (NL → code)
Each factory tool should accept a natural-language `specification: str` and return **complete Python source code** as a string.

```python
def _parse_spec(specification: str) -> dict:
    """Extract entity name, fields, and actions from NL spec."""
    spec = specification.strip()
    entity_match = re.search(r"(?:for|para|entity|entidad)\s+(\w+)", spec, re.I)
    entity = entity_match.group(1) if entity_match else "Entity"
    fields = re.findall(r"\b(\w+)\s*:\s*(str|int|float|bool)", spec, re.I)
    return {"entity": entity, "fields": fields or [("id", "int"), ("name", "str")]}

@mcp.tool()
def controller_factory(specification: str) -> str:
    """Generate REST controller code from a natural language specification."""
    meta = _parse_spec(specification)
    entity = meta["entity"]
    class_name = entity.title().replace("_", "")
    lines = [
        f"class {class_name}Controller:",
        f"    def __init__(self, service: {class_name}Service):",
        "        self._service = service",
        f"    def list_{entity.lower()}s(self) -> list[dict]:",
        f"        return self._service.list_{entity.lower()}s()",
    ]
    return "\\n".join(lines)
```

## NL keywords to detect
- "CRUD", "crear/leer/actualizar/borrar" → generate full CRUD methods
- "FastAPI", "Flask" → adjust route decorators
- field names in spec → generate dataclass or pydantic model fields

## Never do
- Do NOT return `"Layer generated successfully"` — return actual code.
- Do NOT create extra tools beyond what the user requested (e.g. only controller, service, repository).
