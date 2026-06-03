"""Data models for retrieved code context."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextChunk:
    """A single piece of retrieved technical context."""

    source: str
    title: str
    content: str
    score: float = 0.0

    def format(self) -> str:
        return f"### [{self.source}] {self.title}\n{self.content.strip()}"
