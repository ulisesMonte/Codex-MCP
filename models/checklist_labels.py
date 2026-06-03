"""Human-readable labels for MCPRequirement checklist keys (console UI)."""

CHECKLIST_LABELS: dict[str, str] = {
    "mcp_name": "MCP name (snake_case, e.g. `stock_tools`)",
    "description": "Short description of what the MCP does",
    "has_tools_or_resources": "At least one tool or resource",
    "tools_complete": "Each tool has name, parameters, types, and return defined",
    "resources_complete": "Each resource has URI, name, and description",
    "transport_confirmed": "Transport selected (stdio or http)",
    "dependencies_identified": "Pip dependencies listed (or none)",
    "output_mode_confirmed": "Output mode (code_only / deploy_local / deploy_http)",
    "http_port_valid": "Valid HTTP port (if deploy_http)",
}
