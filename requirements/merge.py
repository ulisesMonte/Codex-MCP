"""Merge partial requirement dicts — delegates to domain model."""
from domain.requirements.merger import RequirementMerger, merge_requirement

__all__ = ["RequirementMerger", "merge_requirement"]
