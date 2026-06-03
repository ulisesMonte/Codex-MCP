"""LLM package — Ollama client with automatic model detection and fallback."""
from llm.ollama_client import (
    get_orchestrator_llm,
    get_coder_llm,
    check_ollama_running,
    get_available_ollama_models,
)

__all__ = [
    "get_orchestrator_llm",
    "get_coder_llm",
    "check_ollama_running",
    "get_available_ollama_models",
]
