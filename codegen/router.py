"""Unified design builder — deterministic baseline for every MCP requirement."""
from __future__ import annotations

import re

from codegen.factory import (
    build_microservice_factory_design,
    is_microservice_factory_requirement,
)
from codegen.tool_bodies import (
    build_tool_body,
    get_module_helpers,
    imports_for_requirement,
    signature_for_tool,
    tool_domain,
)
from shared.signatures import params_to_signature
from models.mcp_design import MCPDesign, ResourceImplementation, ToolImplementation
from models.mcp_requirement import MCPRequirement, ParameterSpec, ToolSpec

_STUB_MARKERS = re.compile(
    r"(?:#\s*)?todo:\s*implement|return\s+[\"']stub[\"']|not implemented|"
    r"generated successfully|return f[\"']Executed|^\s*#\s*Implementation\s*$",
    re.I | re.M,
)

_ECHO_STUB_RE = re.compile(
    r'result\s*=\s*\{\s*["\'](?:payload|query|id)["\']\s*:\s*\w+\s*\}',
    re.I,
)


def build_design_from_requirement(req: MCPRequirement) -> MCPDesign:
    """Deterministic, domain-aware design for any requirement (no LLM)."""
    if is_microservice_factory_requirement(req):
        return build_microservice_factory_design(req)

    tools = [build_tool_implementation(t, req) for t in req.tools]
    resources = [build_resource_implementation(r) for r in req.resources]
    has_external = any(
        tool_domain(t, req) in ("bigquery", "database", "http") for t in req.tools
    )

    return MCPDesign(
        requirement=req,
        server_filename=f"{req.mcp_name}_server.py",
        imports=imports_for_requirement(req),
        tools=tools,
        resources=resources,
        has_external_calls=has_external,
        estimated_complexity="medium" if has_external else "simple",
    )


def build_tool_implementation(tool: ToolSpec, req: MCPRequirement) -> ToolImplementation:
    domain = tool_domain(tool, req)
    sig = signature_for_tool(tool, domain)
    if not sig and tool.parameters:
        sig = params_to_signature(tool.parameters)
    return ToolImplementation(
        name=tool.name,
        signature=sig,
        return_type=tool.returns_type or "str",
        description=tool.description or tool.name.replace("_", " "),
        returns_description=tool.returns_description or "Operation result as JSON",
        body=build_tool_body(tool, req, domain),
    )


def build_resource_implementation(resource) -> ResourceImplementation:
    params_sig = params_to_signature(resource.params) if resource.params else ""
    return ResourceImplementation(
        uri_template=resource.uri_template,
        name=resource.name,
        params_signature=params_sig,
        return_type=resource.returns_type,
        description=resource.description,
        body='    return json.dumps({"uri": "' + resource.uri_template + '", "data": "ok"})',
    )


def get_module_helpers(req: MCPRequirement) -> str:
    from codegen.tool_bodies import get_module_helpers as _helpers

    return _helpers(req)


def merge_designs(baseline: MCPDesign, candidate: MCPDesign | None) -> MCPDesign:
    """Keep baseline quality; only accept LLM tools that are strictly stronger."""
    if candidate is None:
        return baseline

    baseline_by_name = {t.name: t for t in baseline.tools}
    merged: list[ToolImplementation] = []

    for ct in candidate.tools:
        bt = baseline_by_name.get(ct.name)
        if bt is None:
            if not is_weak_tool_implementation(ct):
                merged.append(_normalize_tool(ct))
            continue
        if is_weak_tool_implementation(ct) or _tool_score(ct) <= _tool_score(bt):
            merged.append(bt)
        else:
            merged.append(_normalize_tool(ct))

    for bt in baseline.tools:
        if bt.name not in {t.name for t in merged}:
            merged.append(bt)

    imports = list(baseline.imports)
    for imp in candidate.imports:
        if imp not in imports:
            imports.append(imp)

    return baseline.model_copy(
        update={
            "tools": merged,
            "imports": imports,
            "resources": candidate.resources or baseline.resources,
            "has_external_calls": baseline.has_external_calls or candidate.has_external_calls,
            "estimated_complexity": candidate.estimated_complexity or baseline.estimated_complexity,
        }
    )


def is_weak_tool_implementation(tool: ToolImplementation) -> bool:
    if not tool.body or len(tool.body.strip()) < 12:
        return True
    if _STUB_MARKERS.search(tool.body):
        return True
    if _ECHO_STUB_RE.search(tool.body):
        return True
    if "\\n" in tool.body and tool.body.count("\n") <= 1:
        return True
    if tool.name.endswith("_factory") and "specification" not in tool.signature:
        return True
    if tool.name.endswith("_factory") and len(tool.body) < 80:
        return True
    if "specification" in tool.signature and len(tool.body) < 60:
        return True
    if tool.name in ("create", "read", "update", "delete"):
        if "specification" in tool.signature and "_parse_nl_spec" not in tool.body:
            return True
        if "specification" not in tool.signature and "_runtime_store" not in tool.body:
            if _ECHO_STUB_RE.search(tool.body) or 'result = {' in tool.body:
                return True
    return False


def _tool_score(tool: ToolImplementation) -> int:
    score = len(tool.body)
    if "os.getenv" in tool.body:
        score += 40
    if "json.dumps" in tool.body or "return [" in tool.body:
        score += 20
    if "raise ValueError" in tool.body:
        score += 10
    if _STUB_MARKERS.search(tool.body):
        score -= 200
    return score


def _normalize_tool(tool: ToolImplementation) -> ToolImplementation:
    body = tool.body.replace("\\n", "\n").replace("\\t", "\t")
    lines = body.splitlines()
    normalized: list[str] = []
    for line in lines:
        s = line.rstrip()
        if s and not s.startswith((" ", "\t")):
            normalized.append(f"    {s}")
        else:
            normalized.append(s)
    return tool.model_copy(update={"body": "\n".join(normalized)})
