"""Public API for requirement enrichment."""
from requirements.enrichment.pipeline import (
    build_confirmation_message,
    decide_status,
    enrich_requirement,
    finalize_requirement,
    user_facing_gaps,
)
from requirements.enrichment.signals import (
    agent_asked_confirmation,
    combined_user_text,
    is_affirmative,
    user_accepts_proposal,
    user_confirmed,
    user_rejects_proposal,
    user_sent_tool_correction,
)

__all__ = [
    "agent_asked_confirmation",
    "build_confirmation_message",
    "agent_asked_confirmation",
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
