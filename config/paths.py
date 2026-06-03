"""Portable path resolution relative to the project root."""
from __future__ import annotations

import os
from pathlib import Path

# config/paths.py -> project root is parent of config/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    """Root of the mcp-factory repo (override with MCP_FACTORY_ROOT)."""
    override = os.getenv("MCP_FACTORY_ROOT")
    if override:
        return Path(override).resolve()
    return _PROJECT_ROOT


def generated_mcps_dir() -> Path:
    return Path(os.getenv("GENERATED_DIR", get_project_root() / "generated" / "mcps"))


def registry_path() -> Path:
    return Path(os.getenv("REGISTRY_PATH", get_project_root() / "registry" / "mcp_registry.json"))


def event_log_dir() -> Path:
    return Path(os.getenv("EVENT_LOG_DIR", get_project_root() / "logs" / "events"))


def context_knowledge_dir() -> Path:
    return Path(os.getenv("CONTEXT_KNOWLEDGE_DIR", get_project_root() / "context" / "knowledge"))


def awesome_knowledge_dir() -> Path:
    return Path(os.getenv("AWESOME_KNOWLEDGE_DIR", context_knowledge_dir() / "awesome"))


def context_docs_dir() -> Path:
    return Path(os.getenv("CONTEXT_DOCS_DIR", get_project_root() / "context" / "docs"))


def context_discovery_dir() -> Path:
    return Path(os.getenv("CONTEXT_DISCOVERY_DIR", get_project_root() / "context" / "discovery"))


def context_scouted_dir() -> Path:
    return Path(os.getenv("CONTEXT_SCOUTED_DIR", get_project_root() / "context" / "scouted"))


def validated_knowledge_dir() -> Path:
    return Path(
        os.getenv("VALIDATED_KNOWLEDGE_DIR", context_knowledge_dir() / "validated")
    )
