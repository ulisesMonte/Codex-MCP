"""Split requirements/enrichment.py into a package."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "requirements" / "enrichment.py"
OUT = ROOT / "requirements" / "enrichment"
lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def slice_lines(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


HEADER = '''"""Requirements enrichment — infer MCP details from natural language."""
from __future__ import annotations

'''

CONSTANTS = slice_lines(18, 146)
SIGNALS_BODY = slice_lines(149, 218)
ENGINE_BODY = slice_lines(258, 543) + slice_lines(600, 1205)
PIPELINE_BODY = slice_lines(221, 244) + slice_lines(246, 255) + slice_lines(544, 597)

OUT.mkdir(exist_ok=True)

(OUT / "constants.py").write_text(
    '''"""Regex patterns and domain constants for requirement enrichment."""
from __future__ import annotations

import re

from models.mcp_requirement import ParameterSpec

'''
    + CONSTANTS,
    encoding="utf-8",
)

(OUT / "signals.py").write_text(
    HEADER
    + """import difflib
import re

from langchain_core.messages import BaseMessage, HumanMessage

from requirements.enrichment.constants import (
    _AFFIRMATIVE_RE,
    _AFFIRMATIVE_START_RE,
    _AGENT_ASKED_CONFIRM_RE,
    _CONFIRMATION_INTENT_RE,
    _CONFIRM_RE,
    _CONFIRM_TYPO_RE,
    _FACTORY_NAME_RE,
    _USER_REJECT_RE,
    _USER_TOOL_CORRECTION_RE,
)
from shared.messages import last_agent_message

"""
    + SIGNALS_BODY,
    encoding="utf-8",
)

(OUT / "inference.py").write_text(
    HEADER
    + """import re

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

"""
    + ENGINE_BODY,
    encoding="utf-8",
)

(OUT / "pipeline.py").write_text(
    HEADER
    + """from langchain_core.messages import BaseMessage

from models.mcp_requirement import MCPRequirement
from requirements.enrichment.constants import _AGENT_SIDE_CLARIFICATION_RE
from requirements.enrichment.inference import (
    _apply_contextual_short_answer,
    _apply_domain_context,
    _apply_latest_user_tool_corrections,
    _drop_answered_clarifications,
    _ensure_crud_tools_complete,
    _ensure_microservice_factory_complete,
    _ensure_tool_parameters,
    _fill_tool_defaults,
    _filter_clarifications,
    _infer_dependencies,
    _infer_description,
    _infer_mcp_name,
    _infer_output_mode,
    _infer_tool_names,
    _infer_tools_from_natural_language,
    _is_agent_side_clarification,
)
from requirements.enrichment.signals import (
    agent_asked_confirmation,
    combined_user_text,
    user_accepts_proposal,
    user_confirmed,
    user_rejects_proposal,
)
from requirements.intent import apply_intent_to_requirement

"""
    + PIPELINE_BODY,
    encoding="utf-8",
)

(OUT / "__init__.py").write_text(
    '''"""Public API for requirement enrichment."""
from requirements.enrichment.pipeline import (
    build_confirmation_message,
    decide_status,
    enrich_requirement,
    finalize_requirement,
    user_facing_gaps,
)
from requirements.enrichment.signals import (
    combined_user_text,
    is_affirmative,
    user_accepts_proposal,
    user_confirmed,
    user_rejects_proposal,
    user_sent_tool_correction,
)

__all__ = [
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
    encoding="utf-8",
)

SRC.unlink()
print("Split enrichment.py into requirements/enrichment/ package")
