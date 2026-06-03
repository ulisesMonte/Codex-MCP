"""Orchestration settings (no heavy imports — safe for runtime/event modules)."""
from __future__ import annotations

import os


def orchestration_mode() -> str:
    """langgraph (default) | events"""
    return os.getenv("ORCHESTRATION_MODE", "langgraph").strip().lower()


def use_event_orchestration() -> bool:
    return orchestration_mode() == "events"
