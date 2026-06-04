"""AST and structural validation for generated MCP server code."""
from __future__ import annotations

import ast
import importlib.util
import re
from dataclasses import dataclass, field

from shared.progress import agent_note


@dataclass
class ValidationResult:
    """Outcome of validating generated MCP source code."""

    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


class GeneratedCodeValidator:
    """Deterministic checks on generated FastMCP server code (no LLM)."""

    STUB_BODY_RE = re.compile(
        r"(?:#\s*)?TODO:\s*implement|return\s+[\"']stub[\"']|not implemented|"
        r"return f[\"']Executed|^\s*#\s*Implementation\s*$|"
        r'result\s*=\s*\{\s*["\'](?:payload|query|id)["\']\s*:\s*\w+\s*\}',
        re.I | re.M,
    )

    def validate(self, code: str, dependencies: list[str] | None = None) -> ValidationResult:
        deps = dependencies or []
        errors: list[str] = []

        try:
            ast.parse(code)
        except SyntaxError as e:
            return ValidationResult(errors=[f"SyntaxError at line {e.lineno}: {e.msg}"])

        if "from fastmcp import FastMCP" not in code and "import fastmcp" not in code:
            errors.append("Missing FastMCP import: 'from fastmcp import FastMCP'")

        has_tool = "@mcp.tool()" in code
        has_resource = bool(re.search(r"@mcp\.resource\(", code))
        if not has_tool and not has_resource:
            errors.append("No @mcp.tool() or @mcp.resource() decorators found")

        if "FastMCP(" not in code:
            errors.append("Missing FastMCP instance: mcp = FastMCP(...)")

        if 'if __name__ == "__main__"' not in code and "if __name__ == '__main__'" not in code:
            errors.append("Missing entry point: if __name__ == '__main__': mcp.run()")

        errors.extend(self._validate_no_stubs(code))
        self._log_dependency_notes(deps)
        return ValidationResult(errors=errors)

    def _validate_no_stubs(self, code: str) -> list[str]:
        errors: list[str] = []
        if self.STUB_BODY_RE.search(code):
            errors.append("Tool bodies contain TODO/stub placeholders — need real implementations")
        if "_factory" in code:
            for match in re.finditer(r"def\s+(\w+_factory)\(([^)]*)\)", code):
                name, params = match.group(1), match.group(2)
                if "specification" not in params:
                    errors.append(
                        f"Factory tool `{name}` must accept specification: str "
                        f"(got: {params or 'no params'})"
                    )
            if "def _parse_microservice_spec" not in code and "def _emit_repository" not in code:
                if re.search(r"_factory", code) and self.STUB_BODY_RE.search(code):
                    errors.append("Microservice factory missing NL parsing helpers")
        if re.search(r"\\n\s+return", code):
            errors.append("Tool body contains literal \\n instead of real newlines")
        return errors

    def _log_dependency_notes(self, dependencies: list[str]) -> None:
        for dep in dependencies:
            module = self._pip_name_to_import(dep)
            try:
                missing = importlib.util.find_spec(module) is None
            except (ModuleNotFoundError, ValueError, ImportError):
                missing = True
            if missing:
                agent_note(
                    f"Dependencia '{dep}' no instalada aquí "
                    f"(OK — pip install {dep} en el entorno destino)"
                )

    @staticmethod
    def _pip_name_to_import(dep: str) -> str:
        name = dep.strip().split("[")[0].split("==")[0].strip()
        if name.startswith("google-cloud-"):
            suffix = name.removeprefix("google-cloud-").replace("-", "_")
            return f"google.cloud.{suffix}"
        return name.replace("-", "_").split(".")[0]


_default_validator = GeneratedCodeValidator()


def validate_code(code: str, dependencies: list[str] | None = None) -> list[str]:
    return _default_validator.validate(code, dependencies).errors
