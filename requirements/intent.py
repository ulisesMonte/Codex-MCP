"""Generation intent — delegates to domain model."""
from models.mcp_requirement import GenerationIntent
from domain.requirements.intent_resolver import (
    GenerationIntentResolver,
    apply_intent_to_requirement,
    infer_generation_intent,
    resolved_intent,
)

__all__ = [
    "GenerationIntent",
    "GenerationIntentResolver",
    "apply_intent_to_requirement",
    "infer_generation_intent",
    "resolved_intent",
]
