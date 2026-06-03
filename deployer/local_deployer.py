"""Local deployer node for generated MCP servers."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from deployer.process_manager import ProcessManager
from events.types import EventTypes
from models.mcp_requirement import OutputMode
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

console = Console()


def deployer_node(state: "MCPFactoryState") -> "MCPFactoryState":
    """Deploy or present the validated MCP server according to output_mode."""
    generated = state["generated_mcp"]
    req = generated.design.requirement
    mode = req.output_mode

    console.print(f"\n[bold blue]Deployer[/bold blue] - mode: [cyan]{mode.value}[/cyan]")
    publish_event(
        state,
        EventTypes.DEPLOYMENT_STARTED,
        "deployer",
        "Handling generated MCP output",
        payload={"output_mode": mode.value, "transport": req.transport},
    )

    if mode == OutputMode.CODE_ONLY:
        return _handle_code_only(state)
    if mode == OutputMode.DEPLOY_LOCAL:
        return _handle_deploy_local(state)
    if mode == OutputMode.DEPLOY_HTTP:
        return _handle_deploy_http(state)

    error = f"Unknown output mode: {mode}"
    publish_event(
        state,
        EventTypes.DEPLOYMENT_FAILED,
        "deployer",
        error,
        level="error",
        payload={"output_mode": str(mode)},
    )
    return {**state, "error": error}


def _handle_code_only(state: "MCPFactoryState") -> "MCPFactoryState":
    """CODE_ONLY: display generated code and file path."""
    generated = state["generated_mcp"]

    console.print(
        Panel(
            f"[green]MCP server generated successfully![/green]\n\n"
            f"[bold]File:[/bold] {generated.server_path}\n\n"
            f"[bold]To run it:[/bold]\n"
            f"  [cyan]python {generated.server_path}[/cyan]\n\n"
            f"[bold]To connect a client (stdio):[/bold]\n"
            f"  Configure your MCP client to use the above command.",
            title="[bold green]Code Ready[/bold green]",
            border_style="green",
        )
    )

    console.print("\n[dim]-- Generated Code Preview --[/dim]")
    preview_lines = generated.code.split("\n")[:40]
    preview = "\n".join(preview_lines)
    if len(generated.code.split("\n")) > 40:
        preview += "\n# ... (truncated - see full file)"
    console.print(Syntax(preview, "python", theme="monokai", line_numbers=True))

    updated = generated.model_copy(update={"status": "generated"})
    publish_event(
        state,
        EventTypes.CODE_READY,
        "deployer",
        "Generated MCP code is ready",
        payload={"server_path": generated.server_path},
    )
    return {**state, "generated_mcp": updated, "phase": "done", "error": None}


def _handle_deploy_local(state: "MCPFactoryState") -> "MCPFactoryState":
    """DEPLOY_LOCAL: launch MCP server as stdio subprocess."""
    generated = state["generated_mcp"]
    req = generated.design.requirement
    pm = ProcessManager.get()

    existing = pm.status(req.mcp_name)
    if existing and existing.is_alive():
        console.print(f"[yellow]Restarting existing instance of {req.mcp_name}[/yellow]")
        pm.stop(req.mcp_name)

    try:
        proc = pm.start_stdio(req.mcp_name, generated.server_path)
        time.sleep(1.0)
        if not proc.is_alive():
            raise RuntimeError(f"Process exited immediately. Check {generated.server_path} for errors.")

        console.print(
            Panel(
                f"[green]MCP server is running![/green]\n\n"
                f"[bold]Name:[/bold]    {req.mcp_name}\n"
                f"[bold]PID:[/bold]     {proc.pid}\n"
                f"[bold]File:[/bold]    {generated.server_path}\n"
                f"[bold]Transport:[/bold] stdio\n\n"
                f"[bold]Stop it with:[/bold]\n"
                f"  [cyan]mcp-factory stop {req.mcp_name}[/cyan]",
                title="[bold green]Deployed Locally[/bold green]",
                border_style="green",
            )
        )

        updated = generated.model_copy(update={
            "status": "deployed",
            "deployment_pid": proc.pid,
        })
        publish_event(
            state,
            EventTypes.MCP_DEPLOYED,
            "deployer",
            "MCP server deployed locally",
            payload={"pid": proc.pid, "transport": "stdio", "server_path": generated.server_path},
        )
        return {**state, "generated_mcp": updated, "phase": "done", "error": None}

    except Exception as e:
        publish_event(
            state,
            EventTypes.DEPLOYMENT_FAILED,
            "deployer",
            "Local deployment failed",
            level="error",
            payload={"error": str(e), "server_path": generated.server_path},
        )
        console.print(f"[red]Deploy failed: {e}[/red]")
        return {**state, "error": str(e)}


def _handle_deploy_http(state: "MCPFactoryState") -> "MCPFactoryState":
    """DEPLOY_HTTP: launch MCP server as HTTP/SSE subprocess."""
    generated = state["generated_mcp"]
    req = generated.design.requirement
    pm = ProcessManager.get()
    port = req.port

    existing = pm.status(req.mcp_name)
    if existing and existing.is_alive():
        console.print(f"[yellow]Restarting existing instance of {req.mcp_name}[/yellow]")
        pm.stop(req.mcp_name)

    try:
        proc = pm.start_http(req.mcp_name, generated.server_path, port)
        time.sleep(1.5)
        if not proc.is_alive():
            raise RuntimeError(f"HTTP server exited immediately. Check {generated.server_path} for errors.")

        url = f"http://localhost:{port}/sse"
        console.print(
            Panel(
                f"[green]MCP HTTP server is running![/green]\n\n"
                f"[bold]Name:[/bold]    {req.mcp_name}\n"
                f"[bold]PID:[/bold]     {proc.pid}\n"
                f"[bold]URL:[/bold]     {url}\n"
                f"[bold]File:[/bold]    {generated.server_path}\n\n"
                f"[bold]Connect your MCP client to:[/bold]\n"
                f"  [cyan]{url}[/cyan]\n\n"
                f"[bold]Stop it with:[/bold]\n"
                f"  [cyan]mcp-factory stop {req.mcp_name}[/cyan]",
                title="[bold green]Deployed as HTTP API[/bold green]",
                border_style="green",
            )
        )

        updated = generated.model_copy(update={
            "status": "deployed",
            "deployment_pid": proc.pid,
            "deployment_url": url,
        })
        publish_event(
            state,
            EventTypes.MCP_DEPLOYED,
            "deployer",
            "MCP HTTP server deployed",
            payload={
                "pid": proc.pid,
                "transport": "http",
                "url": url,
                "server_path": generated.server_path,
            },
        )
        return {**state, "generated_mcp": updated, "phase": "done", "error": None}

    except Exception as e:
        publish_event(
            state,
            EventTypes.DEPLOYMENT_FAILED,
            "deployer",
            "HTTP deployment failed",
            level="error",
            payload={"error": str(e), "server_path": generated.server_path, "port": port},
        )
        console.print(f"[red]HTTP deploy failed: {e}[/red]")
        return {**state, "error": str(e)}
