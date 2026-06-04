"""Classify and apply generation intent (code_generator / integration / runtime)."""
from __future__ import annotations

import re

from models.mcp_requirement import GenerationIntent, MCPRequirement, ParameterSpec, ToolSpec


class GenerationIntentResolver:
    """Determines what MCP tools should do and aligns tool specs with that intent."""

    NL_SPEC_PARAM = ParameterSpec(
        name="specification",
        type="str",
        description=(
            "Natural language description of what to generate "
            "(entity, fields, operations, framework)"
        ),
    )

    CODE_GEN_SIGNALS = (
        r"generar\s+c[oó]digo",
        r"generate\s+code",
        r"lenguaje natural",
        r"natural language",
        r"\bscaffold\b",
        r"\bplantilla\b",
        r"\btemplate\b",
        r"ayud(?:e|ar)\s+a\s+crear",
        r"help.*creat",
        r"a partir de",
        r"desde\s+(?:texto|prompts?|mcp)",
        r"_factory|\bfactory\b",
        r"crear\s+(?:daos?|clases?|m[oó]dulos?|servicios?|repositorios?)",
        r"emitir\s+c[oó]digo",
        r"escribir\s+c[oó]digo",
        r"write\s+code",
        r"codegen",
    )

    INTEGRATION_SIGNALS = (
        r"bigquery|big query",
        r"postgres(?:ql)?|mysql|mariadb|mongodb|mongo\b|redis|sqlite",
        r"conexi[oó]n|connection|conect",
        r"\bhttp\b|rest api|api externa",
        r"google-cloud",
    )

    RUNTIME_SIGNALS = (
        r"ejecutar|perform|run\s+query",
        r"consultar|query\s+table",
        r"operaciones?\s+sobre\s+(?:registros|datos|records)",
        r"persistir|guardar|almacenar",
    )

    CRUD_OPS = frozenset({"create", "read", "update", "delete"})

    def infer(self, text: str, req: MCPRequirement) -> GenerationIntent:
        """Classify requirement: generate code, integrate external systems, or run operations."""
        lower = (text or "").lower()
        blob = " ".join(
            [
                lower,
                req.description.lower(),
                req.mcp_name.lower(),
                " ".join(t.name for t in req.tools),
                " ".join(t.description.lower() for t in req.tools),
                " ".join(req.dependencies),
            ]
        )

        if any(t.name.endswith("_factory") for t in req.tools):
            return GenerationIntent.CODE_GENERATOR

        if any(re.search(p, blob) for p in self.CODE_GEN_SIGNALS):
            if not re.search(r"plsql|pl/sql|oracle", blob):
                return GenerationIntent.CODE_GENERATOR

        if req.dependencies or any(re.search(p, blob) for p in self.INTEGRATION_SIGNALS):
            if not self._wants_code_generation(blob):
                return GenerationIntent.INTEGRATION

        if any(re.search(p, blob) for p in self.RUNTIME_SIGNALS):
            return GenerationIntent.RUNTIME

        if self._has_crud_tools(req) and self._wants_code_generation(blob):
            return GenerationIntent.CODE_GENERATOR

        if self._has_crud_tools(req):
            return GenerationIntent.RUNTIME

        if re.search(r"generar|generate|crear|create", blob) and not req.dependencies:
            return GenerationIntent.CODE_GENERATOR

        return GenerationIntent.RUNTIME

    def resolve(self, req: MCPRequirement, text: str = "") -> GenerationIntent:
        if req.generation_intent != GenerationIntent.AUTO:
            return req.generation_intent
        return self.infer(text, req)

    def apply(self, req: MCPRequirement, text: str) -> None:
        """Set generation_intent and align tool params/descriptions with intent."""
        intent = self.infer(text, req)
        req.generation_intent = intent

        if intent == GenerationIntent.CODE_GENERATOR:
            self._apply_code_generator_tools(req, text)
        elif intent == GenerationIntent.INTEGRATION:
            self._apply_integration_tools(req)
        elif intent == GenerationIntent.RUNTIME:
            self._apply_runtime_tools(req)

    def _apply_code_generator_tools(self, req: MCPRequirement, text: str) -> None:
        target = self._code_target_label(text, req)
        for tool in req.tools:
            if tool.name.endswith("_factory"):
                if not tool.parameters:
                    tool.parameters = [self.NL_SPEC_PARAM.model_copy(deep=True)]
                continue
            if not tool.parameters or self._params_are_runtime_crud(tool):
                tool.parameters = [self.NL_SPEC_PARAM.model_copy(deep=True)]
            label = tool.name.replace("_", " ")
            tool.description = (
                tool.description
                if "generate" in tool.description.lower() or "genera" in tool.description.lower()
                else f"Generate {label} {target} source code from a natural language specification"
            )
            tool.implementation_hint = (
                f"Parse specification text (entity, fields, operations) and emit complete "
                f"Python code for {label} — never echo inputs or return placeholder JSON"
            )

    def _apply_integration_tools(self, req: MCPRequirement) -> None:
        for tool in req.tools:
            if tool.parameters:
                continue
            hint = (tool.implementation_hint + tool.description + req.description).lower()
            if "connection" in tool.name or "connect" in hint:
                continue
            if "query" in tool.name or "sql" in hint:
                continue

    def _apply_runtime_tools(self, req: MCPRequirement) -> None:
        for tool in req.tools:
            if tool.name == "read" and (
                not tool.parameters or self._single_param_named(tool, "specification")
            ):
                tool.parameters = [
                    ParameterSpec(
                        name="query",
                        type="str",
                        description="Id or filter expression to read records",
                        required=False,
                        default="",
                    )
                ]
            elif tool.name == "delete" and (
                not tool.parameters or self._single_param_named(tool, "specification")
            ):
                tool.parameters = [
                    ParameterSpec(
                        name="record_id",
                        type="str",
                        description="Identifier of the record to delete",
                    )
                ]
            elif tool.name in ("create", "update") and (
                not tool.parameters or self._single_param_named(tool, "specification")
            ):
                tool.parameters = [
                    ParameterSpec(
                        name="payload",
                        type="str",
                        description=f"JSON payload for {tool.name} operation",
                    )
                ]

    def _wants_code_generation(self, text: str) -> bool:
        return any(re.search(p, text) for p in self.CODE_GEN_SIGNALS)

    def _has_crud_tools(self, req: MCPRequirement) -> bool:
        return bool(req.tools) and all(t.name in self.CRUD_OPS for t in req.tools)

    @staticmethod
    def _params_are_runtime_crud(tool: ToolSpec) -> bool:
        names = {p.name for p in tool.parameters}
        return names <= {"payload", "query", "id", "record_id"} and bool(names)

    @staticmethod
    def _single_param_named(tool: ToolSpec, name: str) -> bool:
        return len(tool.parameters) == 1 and tool.parameters[0].name == name

    @staticmethod
    def _code_target_label(text: str, req: MCPRequirement) -> str:
        lower = text.lower()
        if re.search(r"\bdaos?\b", lower):
            return "DAO"
        if re.search(r"repository|repositorio", lower):
            return "repository"
        if re.search(r"service|servicio", lower):
            return "service"
        if re.search(r"controller|controlador", lower):
            return "controller"
        if re.search(r"model|modelo", lower):
            return "model"
        return "component"


_default_resolver = GenerationIntentResolver()


def infer_generation_intent(text: str, req: MCPRequirement) -> GenerationIntent:
    return _default_resolver.infer(text, req)


def resolved_intent(req: MCPRequirement, text: str = "") -> GenerationIntent:
    return _default_resolver.resolve(req, text)


def apply_intent_to_requirement(req: MCPRequirement, text: str) -> None:
    _default_resolver.apply(req, text)
