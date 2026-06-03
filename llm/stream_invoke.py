"""Stream LLM responses with progress callbacks for the CLI."""
from __future__ import annotations

import time
from typing import Any

from cli.ui_context import notify_progress, notify_thinking


def invoke_llm_with_progress(llm: Any, messages: list, *, label: str = "Pensando") -> str:
    """
    Stream tokens from ChatOllama and push thinking/progress updates to the UI.
    Falls back to blocking invoke if streaming is unavailable.
    """
    notify_progress(f"{label} — conectando con Ollama…")
    notify_thinking(f"[dim]{label}…[/dim]")

    started = time.monotonic()
    chunks: list[str] = []
    last_ui = 0.0

    try:
        stream = llm.stream(messages)
    except Exception:
        notify_progress(f"{label} — generando respuesta (modo batch)…")
        response = llm.invoke(messages)
        text = (response.content or "").strip()
        notify_thinking(f"[green]✓[/green] {label} ({len(text)} chars, batch)")
        return text

    for i, chunk in enumerate(stream):
        piece = _chunk_text(chunk)
        if piece:
            chunks.append(piece)
        now = time.monotonic()
        if i == 0 or now - last_ui >= 2.0:
            elapsed = int(now - started)
            size = sum(len(c) for c in chunks)
            dots = "." * ((i // 3) % 4)
            notify_progress(f"{label}{dots} ({elapsed}s · {size} chars)")
            preview = "".join(chunks)[-120:].replace("\n", " ")
            if preview:
                notify_thinking(f"[cyan]{label}[/cyan] [dim]{preview[-80:]}[/dim]")
            last_ui = now

    text = "".join(chunks).strip()
    elapsed = int(time.monotonic() - started)
    notify_progress(f"{label} — parseando JSON ({elapsed}s)…")
    notify_thinking(f"[green]✓[/green] {label} listo ({len(text)} chars)")
    return text


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", chunk)
    if content is None:
        return ""
    return str(content)
