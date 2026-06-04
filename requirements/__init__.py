"""Requirements gathering domain — parsing, enrichment, merge."""
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
