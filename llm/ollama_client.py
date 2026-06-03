"""
Ollama LLM client with automatic model detection and fallback.

Uses a heterogeneous setup:
  - Orchestrator: llama3.3:70b → llama3.1:8b (reasoning, planning, JSON)
  - Coder:        qwen2.5-coder:32b → qwen2.5-coder:7b (code generation)

Falls back gracefully when preferred models are not pulled.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from rich.console import Console

load_dotenv()
console = Console()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

ORCHESTRATOR_MODELS = [
    "llama3.3:70b",
    "llama3.1:70b",
    "llama3.2:3b",
    "llama3.1:8b",
    "qwen2.5:14b",
    "qwen2.5:7b",
    "mistral:7b",
]

CODER_MODELS = [
    "qwen2.5-coder:32b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "codellama:13b",
    "codellama:7b",
]


def get_available_ollama_models() -> list[str]:
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


def check_ollama_running() -> bool:
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return response.status_code == 200
    except Exception:
        return False


def _should_print_console(quiet: bool) -> bool:
    if quiet:
        return False
    try:
        from cli.ui_context import is_quiet_console
        return not is_quiet_console()
    except ImportError:
        return True


def _pick_model(candidates: list[str], role: str, *, quiet: bool = False) -> Optional[str]:
    available = get_available_ollama_models()
    env_key = f"MODEL_{role.upper()}"
    override = os.getenv(env_key)
    if override:
        if override in available:
            if _should_print_console(quiet):
                console.print(f"[cyan]  [env override] {role}: {override}[/cyan]")
            return override
        if _should_print_console(quiet):
            console.print(f"[yellow]  ⚠ {env_key}={override} not found in Ollama — auto-detecting.[/yellow]")

    for model in candidates:
        if model in available:
            return model

    if available:
        if _should_print_console(quiet):
            console.print(
                f"[yellow]  ⚠ No preferred {role} model found. "
                f"Using {available[0]} as fallback.[/yellow]"
            )
        return available[0]

    return None


def get_orchestrator_llm(temperature: float = 0.1, *, quiet: bool = False) -> ChatOllama:
    if not check_ollama_running():
        raise RuntimeError(
            "\n❌ Ollama is not running.\n"
            "   Start it with: ollama serve\n"
            f"   Expected URL: {OLLAMA_BASE_URL}"
        )

    model = _pick_model(ORCHESTRATOR_MODELS, "orchestrator", quiet=quiet)
    if not model:
        raise RuntimeError(
            "\n❌ No models found in Ollama.\n"
            "   Pull one with:  ollama pull llama3.1:8b"
        )

    if _should_print_console(quiet):
        console.print(f"[green]  ✓ Orchestrator → {model}[/green]")
    return ChatOllama(
        model=model,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
    )


def get_coder_llm(temperature: float = 0.05, *, quiet: bool = False) -> ChatOllama:
    if not check_ollama_running():
        raise RuntimeError(
            "\n❌ Ollama is not running.\n"
            "   Start it with: ollama serve"
        )

    model = _pick_model(CODER_MODELS, "coder", quiet=quiet)
    if not model:
        if _should_print_console(quiet):
            console.print(
                "[yellow]  ⚠ No dedicated coder model found. "
                "Falling back to orchestrator model for code generation.[/yellow]"
            )
        return get_orchestrator_llm(temperature=temperature, quiet=True)

    if _should_print_console(quiet):
        console.print(f"[green]  ✓ Code generator → {model}[/green]")
    return ChatOllama(
        model=model,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
    )
