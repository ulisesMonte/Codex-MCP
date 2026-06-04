"""Robust JSON extraction from LLM responses (shared by agents)."""
from __future__ import annotations

import json
import re


def extract_json_dict(text: str) -> dict:
    """
    Parse the first valid JSON object from text.
    Raises ValueError when no object can be parsed.
    """
    data, ok = extract_json(text)
    if ok and data:
        return data
    raise ValueError(f"No valid JSON in response: {text[:400]}")


def extract_json(text: str) -> tuple[dict, bool]:
    """
    Returns (parsed_dict, parse_ok).
    parse_ok is False when only partial regex extraction succeeded.
    """
    text = text.strip()
    candidates = [text]

    for pattern in (r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            candidates.insert(0, m.group(1).strip())

    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group(0))

    for candidate in candidates:
        for loader in (_loads_strict, _loads_relaxed):
            try:
                data = loader(candidate)
                if isinstance(data, dict):
                    return data, True
            except (json.JSONDecodeError, ValueError):
                continue

    partial = _regex_extract_fields(text)
    if partial:
        return partial, False

    return {}, False


def _loads_strict(s: str) -> dict:
    return json.loads(s)


def _loads_relaxed(s: str) -> dict:
    fixed = re.sub(r",\s*}", "}", s)
    fixed = re.sub(r",\s*]", "]", fixed)
    return json.loads(fixed)


def _regex_extract_fields(text: str) -> dict:
    """Best-effort extraction when JSON is malformed."""
    out: dict = {}
    m = re.search(
        r'"message_to_user"\s*:\s*"((?:[^"\\]|\\.)*)"',
        text,
        re.DOTALL,
    )
    if m:
        out["message_to_user"] = bytes(m.group(1), "utf-8").decode("unicode_escape")

    status_m = re.search(r'"status"\s*:\s*"(gathering|complete)"', text)
    if status_m:
        out["status"] = status_m.group(1)

    block = re.search(r'"current_requirement"\s*:\s*(\{[\s\S]*?\})\s*[,}]', text)
    if block:
        try:
            out["current_requirement"] = json.loads(block.group(1))
        except json.JSONDecodeError:
            pass

    return out
