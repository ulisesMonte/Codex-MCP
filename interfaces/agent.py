"""IAgent — Abstract Base Class for all pipeline agents."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState


class IAgent(ABC):
    """
    Single Responsibility: every agent does ONE transformation on the state.
    Open/Closed: new agents extend this without modifying existing code.
    """

    @abstractmethod
    def run(self, state: "MCPFactoryState") -> "MCPFactoryState":
        """
        Execute this agent's task.

        Args:
            state: Current pipeline state (immutable input).

        Returns:
            New state dict with this agent's updates merged in.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name for logging."""
        ...
