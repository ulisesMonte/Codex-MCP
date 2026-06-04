"""One-shot migration: modular package layout (run from repo root)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (old_path relative to ROOT, new_path relative to ROOT)
FILE_MOVES: list[tuple[str, str]] = [
    ("agents/shared/messages.py", "shared/messages.py"),
    ("agents/shared/signatures.py", "shared/signatures.py"),
    ("agents/progress.py", "shared/progress.py"),
    ("agents/requirement_intent.py", "requirements/intent.py"),
    ("agents/requirements_normalize.py", "requirements/normalize.py"),
    ("agents/requirements_merge.py", "requirements/merge.py"),
    ("agents/requirements_response.py", "requirements/response.py"),
    ("agents/requirements_enrichment.py", "requirements/enrichment.py"),
    ("agents/codegen_router.py", "codegen/router.py"),
    ("agents/codegen_core.py", "codegen/core.py"),
    ("agents/tool_codegen.py", "codegen/tool_bodies.py"),
    ("agents/factory_codegen.py", "codegen/factory.py"),
    ("agents/codegen_helpers_runtime.py", "codegen/helpers_runtime.py"),
    ("agents/requirements_agent.py", "agents/requirements/node.py"),
    ("agents/mcp_design_agent.py", "agents/design/node.py"),
    ("agents/mcp_creator_agent.py", "agents/creator/node.py"),
    ("agents/validator_agent.py", "agents/validator/node.py"),
    ("agents/scout_base.py", "agents/scouts/base.py"),
    ("agents/scout_mcp_agent.py", "agents/scouts/mcp.py"),
    ("agents/scout_api_agent.py", "agents/scouts/api.py"),
    ("agents/scout_data_agent.py", "agents/scouts/data.py"),
    ("agents/scout_docs_agent.py", "agents/scouts/docs.py"),
    ("agents/scout_validator_agent.py", "agents/scouts/validator.py"),
]

IMPORT_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bfrom agents\.shared\.messages\b", "from shared.messages"),
    (r"\bfrom agents\.shared\.signatures\b", "from shared.signatures"),
    (r"\bfrom agents\.shared\b", "from shared"),
    (r"\bfrom agents\.progress\b", "from shared.progress"),
    (r"\bfrom agents\.requirement_intent\b", "from requirements.intent"),
    (r"\bfrom agents\.requirements_normalize\b", "from requirements.normalize"),
    (r"\bfrom agents\.requirements_merge\b", "from requirements.merge"),
    (r"\bfrom agents\.requirements_response\b", "from requirements.response"),
    (r"\bfrom agents\.requirements_enrichment\b", "from requirements.enrichment"),
    (r"\bfrom agents\.codegen_router\b", "from codegen.router"),
    (r"\bfrom agents\.codegen_core\b", "from codegen.core"),
    (r"\bfrom agents\.tool_codegen\b", "from codegen.tool_bodies"),
    (r"\bfrom agents\.factory_codegen\b", "from codegen.factory"),
    (r"\bfrom agents\.codegen_helpers_runtime\b", "from codegen.helpers_runtime"),
    (r"\bfrom agents\.requirements_agent\b", "from agents.requirements"),
    (r"\bfrom agents\.mcp_design_agent\b", "from agents.design"),
    (r"\bfrom agents\.mcp_creator_agent\b", "from agents.creator"),
    (r"\bfrom agents\.validator_agent\b", "from agents.validator"),
    (r"\bfrom agents\.scout_base\b", "from agents.scouts.base"),
    (r"\bfrom agents\.scout_mcp_agent\b", "from agents.scouts.mcp"),
    (r"\bfrom agents\.scout_api_agent\b", "from agents.scouts.api"),
    (r"\bfrom agents\.scout_data_agent\b", "from agents.scouts.data"),
    (r"\bfrom agents\.scout_docs_agent\b", "from agents.scouts.docs"),
    (r"\bfrom agents\.scout_validator_agent\b", "from agents.scouts.validator"),
    (r"\bimport agents\.requirements_enrichment\b", "import requirements.enrichment"),
    (r"\bimport agents\.codegen_router\b", "import codegen.router"),
]

# Fix TEMPLATES_DIR in creator after move
CREATOR_TEMPLATES_OLD = 'Path(__file__).parent.parent / "templates"'
CREATOR_TEMPLATES_NEW = 'Path(__file__).resolve().parents[2] / "templates"'

# helpers_runtime path references in factory/codegen - check if any relative paths

INIT_FILES: dict[str, str] = {
    "shared/__init__.py": '''"""Cross-cutting utilities shared across the pipeline."""
from shared.messages import last_agent_message, last_user_message
from shared.signatures import params_to_signature
from shared.progress import agent_note

__all__ = [
    "last_agent_message",
    "last_user_message",
    "params_to_signature",
    "agent_note",
]
''',
    "requirements/__init__.py": '''"""Requirements gathering domain — parsing, enrichment, merge."""
from models.mcp_requirement import GenerationIntent
from requirements.enrichment import (
    build_confirmation_message,
    combined_user_text,
    decide_status,
    enrich_requirement,
    finalize_requirement,
    is_affirmative,
    user_accepts_proposal,
    user_confirmed,
    user_facing_gaps,
    user_rejects_proposal,
    user_sent_tool_correction,
)
from requirements.intent import (
    apply_intent_to_requirement,
    infer_generation_intent,
    resolved_intent,
)
from requirements.merge import merge_requirement
from requirements.normalize import normalize_clarifications
from requirements.response import build_clarification_message, parse_requirements_response

__all__ = [
    "GenerationIntent",
    "apply_intent_to_requirement",
    "infer_generation_intent",
    "resolved_intent",
    "merge_requirement",
    "normalize_clarifications",
    "build_clarification_message",
    "parse_requirements_response",
    "build_confirmation_message",
    "combined_user_text",
    "decide_status",
    "enrich_requirement",
    "finalize_requirement",
    "is_affirmative",
    "user_accepts_proposal",
    "user_confirmed",
    "user_facing_gaps",
    "user_rejects_proposal",
    "user_sent_tool_correction",
]
''',
    "codegen/__init__.py": '''"""MCP code generation — design building and tool bodies."""
from codegen.router import (
    build_design_from_requirement,
    build_resource_implementation,
    build_tool_implementation,
    get_module_helpers,
    is_weak_tool_implementation,
    merge_designs,
)
from codegen.tool_bodies import build_tool_body, imports_for_requirement, tool_domain

__all__ = [
    "build_design_from_requirement",
    "build_resource_implementation",
    "build_tool_implementation",
    "get_module_helpers",
    "is_weak_tool_implementation",
    "merge_designs",
    "build_tool_body",
    "imports_for_requirement",
    "tool_domain",
]
''',
    "agents/requirements/__init__.py": '''"""Requirements gathering agent node."""
from agents.requirements.node import requirements_agent_node

__all__ = ["requirements_agent_node"]
''',
    "agents/design/__init__.py": '''"""MCP design agent node."""
from agents.design.node import _normalize_body, mcp_design_agent_node

__all__ = ["mcp_design_agent_node", "_normalize_body"]
''',
    "agents/creator/__init__.py": '''"""MCP creator agent node."""
from agents.creator.node import mcp_creator_agent_node, _render_code

__all__ = ["mcp_creator_agent_node", "_render_code"]
''',
    "agents/validator/__init__.py": '''"""Code validator agent node."""
from agents.validator.node import validator_agent_node, _validate

__all__ = ["validator_agent_node", "_validate"]
''',
    "agents/scouts/__init__.py": '''"""Parallel scout agent nodes."""
from agents.scouts.api import scout_api_agent_node
from agents.scouts.base import scout_agent_node, scout_docs_agent_node
from agents.scouts.data import scout_data_agent_node
from agents.scouts.docs import scout_docs_agent_node
from agents.scouts.mcp import scout_mcp_agent_node
from agents.scouts.validator import scout_validator_agent_node, _validate_reports

__all__ = [
    "scout_agent_node",
    "scout_docs_agent_node",
    "scout_api_agent_node",
    "scout_data_agent_node",
    "scout_mcp_agent_node",
    "scout_validator_agent_node",
    "_validate_reports",
]
''',
    "agents/__init__.py": '''"""Pipeline agent nodes (LangGraph / event handlers)."""
from agents.creator import mcp_creator_agent_node
from agents.design import mcp_design_agent_node
from agents.requirements import requirements_agent_node
from agents.scouts import (
    scout_api_agent_node,
    scout_data_agent_node,
    scout_docs_agent_node,
    scout_mcp_agent_node,
    scout_validator_agent_node,
)
from agents.validator import validator_agent_node

__all__ = [
    "requirements_agent_node",
    "scout_mcp_agent_node",
    "scout_api_agent_node",
    "scout_data_agent_node",
    "scout_docs_agent_node",
    "scout_validator_agent_node",
    "mcp_design_agent_node",
    "mcp_creator_agent_node",
    "validator_agent_node",
]
''',
}


def move_files() -> None:
    for old_rel, new_rel in FILE_MOVES:
        old = ROOT / old_rel
        new = ROOT / new_rel
        if not old.exists():
            print(f"SKIP missing: {old_rel}")
            continue
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)
        print(f"COPY {old_rel} -> {new_rel}")


def apply_import_rewrites(content: str) -> str:
    for pattern, repl in IMPORT_REPLACEMENTS:
        content = re.sub(pattern, repl, content)
    content = content.replace(CREATOR_TEMPLATES_OLD, CREATOR_TEMPLATES_NEW)
    return content


def rewrite_all_py_files() -> None:
    for path in ROOT.rglob("*.py"):
        if ".git" in path.parts or ".venv" in path.parts or "scripts" in path.parts:
            continue
        if path.name == "restructure_packages.py":
            continue
        text = path.read_text(encoding="utf-8")
        new_text = apply_import_rewrites(text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"REWRITE {path.relative_to(ROOT)}")


def write_init_files() -> None:
    for rel, content in INIT_FILES.items():
        path = ROOT / rel
        path.write_text(content, encoding="utf-8")
        print(f"WRITE {rel}")


def remove_old_files() -> None:
    old_paths = [ROOT / old for old, _ in FILE_MOVES]
    old_paths.extend([
        ROOT / "agents/shared/__init__.py",
        ROOT / "agents/shared",
    ])
    for old in FILE_MOVES:
        p = ROOT / old[0]
        if p.exists():
            p.unlink()
            print(f"DELETE {old[0]}")
    shared_dir = ROOT / "agents/shared"
    if shared_dir.exists() and not any(shared_dir.iterdir()):
        shared_dir.rmdir()
        print("DELETE agents/shared/")


def update_pyproject() -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    for pkg in ("shared", "requirements", "codegen"):
        if f'    "{pkg}",' not in text:
            text = text.replace(
                'packages = [\n    "agents",',
                f'packages = [\n    "agents",\n    "{pkg}",',
                1,
            )
    path.write_text(text, encoding="utf-8")
    print("UPDATE pyproject.toml")


def main() -> None:
    move_files()
    write_init_files()
    rewrite_all_py_files()
    remove_old_files()
    update_pyproject()
    print("Done.")


if __name__ == "__main__":
    main()
