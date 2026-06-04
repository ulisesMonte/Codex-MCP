"""Parallel scout execution — mirrors LangGraph fan-out in event mode."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from shared.parallel import AgentThreadPool

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

ScoutNode = Callable[["MCPFactoryState"], "MCPFactoryState"]


def run_scouts_parallel(
    state: MCPFactoryState,
    scout_nodes: tuple[ScoutNode, ...],
    *,
    max_workers: int = 4,
) -> MCPFactoryState:
    """Run scout nodes concurrently on the same input snapshot; merge reports."""
    if not scout_nodes:
        return {}

    pool = AgentThreadPool(max_workers=max_workers)
    results = pool.map(lambda node: node(state), list(scout_nodes))

    reports: list = []
    for result in results:
        reports.extend(result.get("scout_reports") or [])

    return {"scout_reports": reports}
