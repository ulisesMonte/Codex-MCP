"""JSONL event store for local append-only event logs."""
from __future__ import annotations

import json
from pathlib import Path

from config.paths import event_log_dir
from events.model import MCPEvent


EVENT_LOG_DIR = event_log_dir()


class JsonlEventStore:
    """Append/read MCP events from logs/events/{session_id}.jsonl."""

    def __init__(self, base_dir: Path | str = EVENT_LOG_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append(self, event: MCPEvent) -> None:
        path = self._path_for(event.session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def read_session(self, session_id: str) -> list[MCPEvent]:
        path = self._path_for(session_id)
        if not path.exists():
            return []

        events: list[MCPEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(MCPEvent.model_validate(json.loads(line)))
        return events

    def list_sessions(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return sorted(path.stem for path in self.base_dir.glob("*.jsonl"))

    def next_sequence(self, session_id: str) -> int:
        events = self.read_session(session_id)
        if not events:
            return 1
        return max(event.sequence for event in events) + 1

    def _path_for(self, session_id: str) -> Path:
        safe_session = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_id)
        return self.base_dir / f"{safe_session}.jsonl"
