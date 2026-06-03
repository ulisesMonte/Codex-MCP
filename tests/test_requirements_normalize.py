from agents.requirements_agent import _merge_requirement
from agents.requirements_normalize import normalize_clarifications


def test_normalize_clarification_dict():
    raw = [{"question": "¿Qué tipo de auth?", "type": "open"}]
    assert normalize_clarifications(raw) == ["¿Qué tipo de auth?"]


def test_merge_accepts_dict_clarifications():
    req = _merge_requirement(
        {
            "mcp_name": "source_connection",
            "description": "BigQuery source",
            "tools": [],
            "clarifications_needed": [
                {"question": "¿Confirmás el nombre 'source'?", "type": "open"},
            ],
        },
        None,
    )
    assert all(isinstance(c, str) for c in req.clarifications_needed)
    assert "Confirmás" in req.clarifications_needed[0] or "Confirm" in req.clarifications_needed[0]
