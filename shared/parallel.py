"""Thread pool utilities for parallel agent workloads."""
from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

_DEFAULT_WORKERS = int(os.getenv("AGENT_THREAD_POOL_SIZE", "4"))


class AgentThreadPool:
    """Shared executor for I/O-bound agent tasks (RAG, scouts, LLM prep)."""

    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers or _DEFAULT_WORKERS

    def run_parallel(
        self,
        tasks: dict[str, Callable[[], T]],
    ) -> dict[str, T]:
        """Run named tasks concurrently; returns results keyed by task name."""
        if not tasks:
            return {}
        if len(tasks) == 1:
            name, fn = next(iter(tasks.items()))
            return {name: fn()}

        workers = min(self.max_workers, len(tasks))
        results: dict[str, T] = {}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agent") as pool:
            futures: dict[Future[T], str] = {
                pool.submit(fn): name for name, fn in tasks.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                results[name] = future.result()
        return results

    def map(
        self,
        fn: Callable[[T], R],
        items: list[T],
        *,
        max_workers: int | None = None,
    ) -> list[R]:
        """Apply fn to each item in parallel (order preserved)."""
        if not items:
            return []
        if len(items) == 1:
            return [fn(items[0])]

        workers = min(max_workers or self.max_workers, len(items))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agent") as pool:
            return list(pool.map(fn, items))


_default_pool = AgentThreadPool()


def run_agent_tasks(tasks: dict[str, Callable[[], T]]) -> dict[str, T]:
    return _default_pool.run_parallel(tasks)


def map_agent_tasks(fn: Callable[[T], R], items: list[T]) -> list[R]:
    return _default_pool.map(fn, items)
