"""Orchestrates MCP code generation: template render + optional LLM repair."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import HumanMessage, SystemMessage

from config.paths import generated_mcps_dir
from context.service import format_context_for_prompt, retrieve_codegen_context
from domain.codegen.design_builder import DeterministicDesignBuilder
from domain.session import MCPFactorySession
from llm.ollama_client import get_coder_llm
from models.mcp_design import GeneratedMCP, MCPDesign
from shared.parallel import AgentThreadPool
from shared.progress import agent_note

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
GENERATED_DIR = generated_mcps_dir()

_STRUCTURAL_ERROR_MARKERS = (
    "Missing FastMCP",
    "No @mcp.tool",
    "Missing FastMCP instance",
    "Missing entry point",
)


@dataclass
class CreatorResult:
    """Output of the code generation phase."""

    generated: GeneratedMCP
    active_design: MCPDesign
    error: str | None = None


class CreatorService:
    """Application service: MCPDesign → GeneratedMCP on disk."""

    def __init__(
        self,
        builder: DeterministicDesignBuilder | None = None,
        pool: AgentThreadPool | None = None,
    ) -> None:
        self.builder = builder or DeterministicDesignBuilder()
        self.pool = pool or AgentThreadPool()

    def generate(self, session: MCPFactorySession) -> CreatorResult:
        design = session.design
        if design is None:
            raise ValueError("No design in session")

        attempt = session.validation_attempts
        prev_errors: list[str] = []
        if attempt > 0 and session.generated_mcp:
            prev_errors = list(session.generated_mcp.validation_errors)

        active_design = design
        code = self.render_code(active_design, prev_errors)

        if prev_errors:
            code, active_design = self._handle_retry(active_design, code, prev_errors, attempt)

        server_path = self.write_to_disk(active_design.server_filename, code)
        generated = GeneratedMCP(
            design=active_design,
            code=code,
            server_path=str(server_path),
            status="generated",
            validation_passed=False,
        )
        return CreatorResult(generated=generated, active_design=active_design)

    def _handle_retry(
        self,
        design: MCPDesign,
        code: str,
        prev_errors: list[str],
        attempt: int,
    ) -> tuple[str, MCPDesign]:
        stub_errors = any(
            "stub" in e.lower() or "specification" in e.lower() or "todo" in e.lower()
            for e in prev_errors
        )
        if stub_errors:
            agent_note("Reconstruyendo design determinístico (implementación débil)")
            active = self.builder.build(design.requirement)
            return self.render_code(active, []), active

        if self.errors_are_structural(prev_errors):
            agent_note("Re-render desde plantilla FastMCP (errores estructurales)")
            return self.render_code(design, []), design

        agent_note("Enviando feedback del validador al coder model…")
        repaired = self.repair_with_llm(design, code, prev_errors)
        if self.has_fastmcp_structure(repaired):
            return repaired, design

        agent_note("Reparación LLM perdió estructura FastMCP — plantilla original")
        return self.render_code(design, []), design

    def render_code(self, design: MCPDesign, prev_errors: list[str] | None = None) -> str:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        transport = design.requirement.transport
        template_name = (
            "mcp_server_http.py.j2" if transport == "http" else "mcp_server_stdio.py.j2"
        )
        template = env.get_template(template_name)
        module_helpers = self.builder.module_helpers(design.requirement)
        return template.render(
            mcp_name=design.requirement.mcp_name,
            description=design.requirement.description,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            imports=design.imports,
            module_helpers=module_helpers,
            tools=design.tools,
            resources=design.resources,
            port=design.requirement.port,
            dependencies=design.requirement.dependencies,
            prev_errors=prev_errors or [],
        )

    def repair_with_llm(self, design: MCPDesign, code: str, errors: list[str]) -> str:
        system_prompt = """You repair Python FastMCP server code.
Return only the complete corrected Python source code.
Do not include markdown, explanations, diffs, or comments about the repair.
You MUST keep: from fastmcp import FastMCP, mcp = FastMCP(...), @mcp.tool() decorators,
and if __name__ == "__main__": mcp.run().
Keep the same MCP tools, resources, transport, and public signatures unless fixing syntax requires otherwise."""

        prompt = (
            "The generated MCP server failed validation.\n\n"
            f"Requirement:\n{design.requirement.model_dump_json(indent=2)}\n\n"
            f"Design:\n{design.model_dump_json(indent=2)}\n\n"
            f"Validation errors:\n{errors}\n\n"
            f"Current code:\n```python\n{code}\n```\n\n"
        )

        rag_future = self.pool.run_parallel(
            {
                "rag": lambda: format_context_for_prompt(
                    retrieve_codegen_context(
                        f"{design.requirement.mcp_name} fastmcp "
                        f"{' '.join(t.name for t in design.tools)}",
                        dependencies=design.requirement.dependencies,
                        limit=6,
                    )
                ),
            }
        )
        rag = rag_future.get("rag", "")
        if rag:
            prompt += f"{rag}\n\n"
        prompt += (
            "Return the full corrected Python file with real implementations "
            "(no placeholder success strings). Preserve the FastMCP server structure."
        )

        try:
            llm = get_coder_llm(temperature=0.02, quiet=True)
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ])
            repaired = self.extract_python_code(response.content)
            if repaired.strip():
                return repaired
        except Exception as e:
            agent_note(f"Reparación LLM falló, manteniendo plantilla: {e}")

        return code

    @staticmethod
    def extract_python_code(text: str) -> str:
        raw = text.strip()
        fenced = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", raw)
        if fenced:
            return fenced.group(1).strip() + "\n"
        return raw + ("\n" if raw else "")

    @staticmethod
    def write_to_disk(filename: str, code: str) -> Path:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        path = GENERATED_DIR / filename
        path.write_text(code, encoding="utf-8")
        return path

    @staticmethod
    def errors_are_structural(errors: list[str]) -> bool:
        return any(
            any(marker in err for marker in _STRUCTURAL_ERROR_MARKERS) for err in errors
        )

    @staticmethod
    def has_fastmcp_structure(code: str) -> bool:
        if "from fastmcp import FastMCP" not in code and "import fastmcp" not in code:
            return False
        if "FastMCP(" not in code:
            return False
        has_tool = "@mcp.tool()" in code
        has_resource = bool(re.search(r"@mcp\.resource\(", code))
        if not has_tool and not has_resource:
            return False
        if '__name__ == "__main__"' not in code and "__name__ == '__main__'" not in code:
            return False
        return True
