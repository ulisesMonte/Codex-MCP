"""Helpers for stable terminal UI during the industrial pipeline."""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from agents.requirements_enrichment import (
    agent_asked_confirmation,
    user_accepts_proposal,
    user_confirmed,
    user_rejects_proposal,
)

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState


def will_run_full_pipeline(state: MCPFactoryState, user_input: str) -> bool:
    """True when this turn will run scouts → design → creator (not just chat)."""
    if user_rejects_proposal(user_input):
        return False
    if state.get("phase") == "complete":
        return True
    req = state.get("requirement")
    if req is None or not req.is_ready():
        return False
    if user_confirmed(user_input):
        return True
    messages = state.get("messages") or []
    return agent_asked_confirmation(messages) and user_accepts_proposal(user_input)


def strip_rich_markup(text: str) -> str:
    return re.sub(r"\[[/\w]+\]", "", text).strip()


class ThrottledRefresher:
    """Avoid flooding the terminal with full redraws (Windows Live bug)."""

    def __init__(self, min_interval_s: float = 2.0) -> None:
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def should_refresh(self) -> bool:
        now = time.monotonic()
        if now - self._last >= self.min_interval_s:
            self._last = now
            return True
        return False

    def reset(self) -> None:
        self._last = 0.0

    def mark_refreshed(self) -> None:
        """Record that a redraw just happened (e.g. manual print_screen)."""
        self._last = time.monotonic()
