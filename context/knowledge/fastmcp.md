# FastMCP — technical reference

## Tool decorator
```python
from fastmcp import FastMCP
mcp = FastMCP("name", description="...")

@mcp.tool()
def my_tool(param: str) -> str:
    """Docstring becomes tool description for the LLM client."""
    return result
```

## Rules
- Tool functions must have type hints on all parameters and return type.
- Use `os.getenv("VAR_NAME")` for secrets — never hardcode API keys.
- Return structured data as JSON strings when the consumer expects text.
- For code-generation tools: accept `specification: str` (natural language) and return generated source code as `str`.

## Entry point (stdio)
```python
if __name__ == "__main__":
    mcp.run()
```

## Common imports
```python
import os
import json
import re
from typing import Optional
import httpx  # for HTTP APIs
```
