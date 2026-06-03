"""
Process Manager - tracks MCP server processes running locally.

It keeps subprocess handles for the current Python session and can reattach
process metadata from the registry by PID for later CLI invocations.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console

console = Console()


@dataclass
class MCPProcess:
    name: str
    pid: int
    server_path: str
    transport: str
    port: Optional[int] = None
    url: Optional[str] = None
    process: Optional[subprocess.Popen] = field(default=None, repr=False)

    def is_alive(self) -> bool:
        if self.process is not None:
            return self.process.poll() is None
        if not self.pid:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False

    def stop(self) -> None:
        if self.process and self.is_alive():
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            console.print(f"[yellow]  Stopped: {self.name} (PID {self.pid})[/yellow]")
            return

        if self.is_alive():
            os.kill(self.pid, signal.SIGTERM)
            console.print(f"[yellow]  Stopped: {self.name} (PID {self.pid})[/yellow]")


class ProcessManager:
    """Singleton-style manager for MCP server processes."""

    _instance: Optional["ProcessManager"] = None
    _processes: dict[str, MCPProcess] = {}

    @classmethod
    def get(cls) -> "ProcessManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_stdio(self, name: str, server_path: str) -> MCPProcess:
        """Launch an MCP server with stdio transport as a background subprocess."""
        proc = subprocess.Popen(
            [sys.executable, server_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        mcp_proc = MCPProcess(
            name=name,
            pid=proc.pid,
            server_path=server_path,
            transport="stdio",
            process=proc,
        )
        self._processes[name] = mcp_proc
        return mcp_proc

    def start_http(self, name: str, server_path: str, port: int) -> MCPProcess:
        """Launch an MCP server with HTTP/SSE transport on the given port."""
        proc = subprocess.Popen(
            [sys.executable, server_path, "--transport", "http", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        url = f"http://localhost:{port}/sse"
        mcp_proc = MCPProcess(
            name=name,
            pid=proc.pid,
            server_path=server_path,
            transport="http",
            port=port,
            url=url,
            process=proc,
        )
        self._processes[name] = mcp_proc
        return mcp_proc

    def attach(
        self,
        name: str,
        pid: int,
        server_path: str,
        transport: str,
        port: Optional[int] = None,
        url: Optional[str] = None,
    ) -> MCPProcess:
        """Track an already-started process from persisted registry metadata."""
        mcp_proc = MCPProcess(
            name=name,
            pid=pid,
            server_path=server_path,
            transport=transport,
            port=port,
            url=url,
        )
        self._processes[name] = mcp_proc
        return mcp_proc

    def stop(self, name: str) -> bool:
        proc = self.status(name)
        if proc:
            proc.stop()
            self._processes.pop(name, None)
            return True
        return False

    def status(self, name: str) -> Optional[MCPProcess]:
        proc = self._processes.get(name)
        if proc and not proc.is_alive():
            self._processes.pop(name, None)
            return None
        return proc

    def list_all(self) -> list[MCPProcess]:
        return [proc for proc in self._processes.values() if proc.is_alive()]

    def stop_all(self) -> None:
        for proc in list(self._processes.values()):
            proc.stop()
        self._processes.clear()
