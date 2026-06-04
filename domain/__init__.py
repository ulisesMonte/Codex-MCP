"""Domain layer — business rules modeled as classes (POO)."""
from domain.codegen.design_builder import DeterministicDesignBuilder
from domain.codegen.code_validator import GeneratedCodeValidator, ValidationResult
from domain.research.scout_validator import ScoutResearchValidator
from domain.requirements.conversation import ConversationSignals, RequirementLifecycle
from domain.requirements.enricher import RequirementEnricher
from domain.requirements.intent_resolver import GenerationIntentResolver
from domain.requirements.merger import RequirementMerger
from domain.session import MCPFactorySession

__all__ = [
    "ConversationSignals",
    "DeterministicDesignBuilder",
    "GeneratedCodeValidator",
    "GenerationIntentResolver",
    "MCPFactorySession",
    "RequirementEnricher",
    "RequirementLifecycle",
    "RequirementMerger",
    "ScoutResearchValidator",
    "ValidationResult",
]
