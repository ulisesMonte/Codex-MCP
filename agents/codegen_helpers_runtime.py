"""Runtime helpers embedded into generated code-generator MCP servers."""


def _parse_nl_spec(specification: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Parse entity, typed fields and CRUD ops from NL (Spanish/English)."""
    import re

    entity = "entity"
    skip = {"a", "an", "un", "una", "the", "el", "la", "for", "para", "de", "del", "mcp", "tool", "dao"}
    for pat in (
        r"(?:entity|entidad|modelo|model|tabla|table|dao|recurso|resource)\s*[:=]?\s*(\w+)",
        r"(?:for|para|de|del|la|el|un|una)\s+(\w+)\s+(?:dao|class|clase|repository|service|controller)",
        r"(?:create|crear|generar|generate)\s+(?:a|an|un|una)?\s*(\w+)",
        r"\b([A-Z][a-zA-Z0-9]+)\b",
    ):
        m = re.search(pat, specification, re.I)
        if m:
            word = m.group(1).lower()
            if word not in skip and len(word) > 2:
                entity = word
                break

    fields: list[tuple[str, str]] = []
    fm = re.search(
        r"(?:fields?|campos?|atributos?|columns?|columnas?)\s*[:=\-]?\s*([^\n.]+)",
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


def _py_type(type_hint: str) -> str:
    return {"int": "int", "str": "str", "bool": "bool", "float": "float"}.get(type_hint.lower(), "str")


def _field_lines(fields: list[tuple[str, str]], indent: str = "    ") -> str:
    lines = [f"{indent}{name}: {_py_type(typ)}" for name, typ in fields]
    return "\n".join(lines) if lines else f"{indent}id: int\n{indent}name: str"


def _emit_crud_method(entity_pascal: str, entity: str, fields: list[tuple[str, str]], op: str) -> str:
    """Emit a single CRUD DAO class as Python source text."""
    import textwrap

    field_block = _field_lines(fields, indent="        ")
    if op == "create":
        tpl = """
            from dataclasses import dataclass
            from typing import Any

            @dataclass
            class {entity_pascal}:
            {field_block}

            class {entity_pascal}Dao:
                def __init__(self) -> None:
                    self._store: dict[int, {entity_pascal}] = {{}}
                    self._seq = 0

                def create(self, data: dict[str, Any]) -> {entity_pascal}:
                    self._seq += 1
                    kwargs = {{k: data.get(k, getattr({entity_pascal}, k, None)) for k, _ in {fields_repr}}}
                    item = {entity_pascal}(**kwargs)
                    self._store[self._seq] = item
                    return item
            """
        fields_repr = repr([n for n, _ in fields] or ["id", "name"])
        return textwrap.dedent(
            tpl.format(entity_pascal=entity_pascal, field_block=field_block, fields_repr=fields_repr)
        ).strip()

    if op == "read":
        tpl = """
            from dataclasses import dataclass, asdict

            @dataclass
            class {entity_pascal}:
            {field_block}

            class {entity_pascal}Dao:
                def __init__(self, store: dict[int, {entity_pascal}] | None = None) -> None:
                    self._store = store or {{}}

                def get(self, record_id: int) -> {entity_pascal} | None:
                    return self._store.get(record_id)

                def list(self, filter_query: str = "") -> list[{entity_pascal}]:
                    items = list(self._store.values())
                    if not filter_query:
                        return items
                    q = filter_query.lower()
                    return [i for i in items if q in str(asdict(i)).lower()]
            """
        return textwrap.dedent(tpl.format(entity_pascal=entity_pascal, field_block=field_block)).strip()

    if op == "update":
        tpl = """
            from dataclasses import dataclass
            from typing import Any

            @dataclass
            class {entity_pascal}:
            {field_block}

            class {entity_pascal}Dao:
                def __init__(self, store: dict[int, {entity_pascal}] | None = None) -> None:
                    self._store = store or {{}}

                def update(self, record_id: int, data: dict[str, Any]) -> {entity_pascal} | None:
                    current = self._store.get(record_id)
                    if current is None:
                        return None
                    merged = {{**current.__dict__, **data, "id": record_id}}
                    self._store[record_id] = {entity_pascal}(**merged)
                    return self._store[record_id]
            """
        return textwrap.dedent(tpl.format(entity_pascal=entity_pascal, field_block=field_block)).strip()

    if op == "delete":
        tpl = """
            from dataclasses import dataclass

            @dataclass
            class {entity_pascal}:
            {field_block}

            class {entity_pascal}Dao:
                def __init__(self, store: dict[int, {entity_pascal}] | None = None) -> None:
                    self._store = store or {{}}

                def delete(self, record_id: int) -> bool:
                    return self._store.pop(record_id, None) is not None
            """
        return textwrap.dedent(tpl.format(entity_pascal=entity_pascal, field_block=field_block)).strip()

    return f"# Unsupported operation: {op}"


def _emit_component(entity_pascal: str, entity: str, fields: list[tuple[str, str]], label: str) -> str:
    import textwrap

    field_block = _field_lines(fields, indent="        ")
    suffix = label.title().replace(" ", "")
    tpl = """
        from dataclasses import dataclass

        @dataclass
        class {entity_pascal}:
        {field_block}

        class {entity_pascal}{suffix}:
            # Generated {label} for {entity_pascal}

            def __init__(self) -> None:
                self.entity = "{entity}"

            def build(self) -> str:
                return f"{{self.__class__.__name__}}(entity={{self.entity!r}})"
        """
    return textwrap.dedent(
        tpl.format(
            entity_pascal=entity_pascal,
            entity=entity,
            field_block=field_block,
            suffix=suffix,
            label=label,
        )
    ).strip()


def _runtime_store(entity: str = "default") -> dict:
    if not hasattr(_runtime_store, "_stores"):
        _runtime_store._stores = {}
    if entity not in _runtime_store._stores:
        _runtime_store._stores[entity] = {}
    return _runtime_store._stores[entity]
