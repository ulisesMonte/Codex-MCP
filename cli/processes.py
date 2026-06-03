"""CLI helpers for process registry reattachment."""
from __future__ import annotations

from deployer.process_manager import ProcessManager


def attach_registered_process(entry: dict):
    """Return an in-memory or registry-backed process handle for an MCP entry."""
    pm = ProcessManager.get()
    name = entry.get("name", "")
    proc = pm.status(name)
    if proc:
        return proc

    pid = entry.get("deployment_pid")
    if not pid:
        return None

    url = entry.get("deployment_url")
    port = entry.get("port")
    if not url and port:
        url = f"http://localhost:{port}/sse"

    try:
        proc = pm.attach(
            name=name,
            pid=int(pid),
            server_path=entry.get("server_path", ""),
            transport=entry.get("transport", "stdio"),
            port=port,
            url=url,
        )
    except (TypeError, ValueError):
        return None

    return proc if proc.is_alive() else None
