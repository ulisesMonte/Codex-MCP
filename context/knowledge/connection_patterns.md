# Database connection MCP patterns

## Postgres connection tool
```python
import os
import json

@mcp.tool()
def create_connection(connection_string: str | None = None) -> str:
    """Validate and return PostgreSQL connection config (no password in output)."""
    dsn = connection_string or os.getenv("DATABASE_URL", "")
    if not dsn:
        return json.dumps({"ok": False, "error": "DATABASE_URL not set"})
    try:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.close()
        return json.dumps({"ok": True, "host": dsn.split("@")[-1].split("/")[0]})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})
```

## BigQuery query tool
```python
from google.cloud import bigquery
import os
import json

@mcp.tool()
def query_bigquery(sql: str) -> str:
    project = os.getenv("GCP_PROJECT", "")
    client = bigquery.Client(project=project)
    rows = [dict(row) for row in client.query(sql).result()]
    return json.dumps(rows, default=str)
```

## Dependencies
- postgres: `psycopg2-binary`
- bigquery: `google-cloud-bigquery`
- mongodb: `pymongo`
