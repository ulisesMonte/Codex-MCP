"""Code-context retrieval (RAG) for MCP Factory agents — Option C hybrid."""
from context.service import (
    format_context_for_prompt,
    format_discovery_for_prompt,
    retrieve_codegen_context,
    retrieve_context,
    search_discovery,
    search_knowledge,
)

__all__ = [
    "retrieve_context",
    "retrieve_codegen_context",
    "search_knowledge",
    "search_discovery",
    "format_context_for_prompt",
    "format_discovery_for_prompt",
]
