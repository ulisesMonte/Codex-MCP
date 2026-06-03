"""Thread-safe UI hooks for Live console sessions (progress + thinking log)."""
from __future__ import annotations

from contextvars import ContextVar
from typing import Callable

ProgressCallback = Callable[[str], None]
ThinkingCallback = Callable[[str], None]

_progress_cb: ContextVar[ProgressCallback | None] = ContextVar("ui_progress", default=None)
_thinking_cb: ContextVar[ThinkingCallback | None] = ContextVar("ui_thinking", default=None)
_quiet_console: ContextVar[bool] = ContextVar("ui_quiet_console", default=False)


def set_ui_callbacks(
    *,
    progress: ProgressCallback | None = None,
    thinking: ThinkingCallback | None = None,
    quiet_console: bool = False,
) -> tuple[object, object, object]:
    """Returns tokens to reset via reset_ui_callbacks."""
    t1 = _progress_cb.set(progress)
    t2 = _thinking_cb.set(thinking)
    t3 = _quiet_console.set(quiet_console)
    return t1, t2, t3


def reset_ui_callbacks(t1: object, t2: object, t3: object) -> None:
    _progress_cb.reset(t1)
    _thinking_cb.reset(t2)
    _quiet_console.reset(t3)


def notify_progress(message: str) -> None:
    cb = _progress_cb.get()
    if cb is not None:
        cb(message)


def notify_thinking(message: str) -> None:
    cb = _thinking_cb.get()
    if cb is not None:
        from cli.pipeline_ui import strip_rich_markup
        cb(strip_rich_markup(message))


def is_quiet_console() -> bool:
    return _quiet_console.get()
