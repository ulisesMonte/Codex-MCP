"""User conversation signals and requirement lifecycle decisions."""
from __future__ import annotations

import difflib
import re

from langchain_core.messages import BaseMessage, HumanMessage

from models.mcp_requirement import MCPRequirement
from requirements.enrichment.constants import (
    _AFFIRMATIVE_RE,
    _AFFIRMATIVE_START_RE,
    _AGENT_ASKED_CONFIRM_RE,
    _AGENT_SIDE_CLARIFICATION_RE,
    _CONFIRMATION_INTENT_RE,
    _CONFIRM_RE,
    _CONFIRM_TYPO_RE,
    _FACTORY_NAME_RE,
    _USER_REJECT_RE,
    _USER_TOOL_CORRECTION_RE,
)
from shared.messages import last_agent_message


class ConversationSignals:
    """Interprets user messages (confirm, reject, corrections, affirmatives)."""

    def combined_user_text(self, messages: list[BaseMessage]) -> str:
        parts = [
            str(m.content).strip()
            for m in messages
            if isinstance(m, HumanMessage) and m.content
        ]
        return "\n".join(parts)

    def user_confirmed(self, text: str) -> bool:
        t = text.strip()
        if _CONFIRM_RE.match(t) or _CONFIRM_TYPO_RE.match(t):
            return True
        normalized = re.sub(r"[^a-z]", "", t.lower())
        return bool(
            normalized
            and difflib.get_close_matches(
                normalized, ("confirm", "confirmar"), n=1, cutoff=0.72
            )
        )

    def is_affirmative(self, text: str) -> bool:
        t = text.strip()
        if _AFFIRMATIVE_RE.match(t):
            return True
        return bool(_AFFIRMATIVE_START_RE.match(t))

    def user_rejects_proposal(self, text: str) -> bool:
        t = text.strip()
        if not t or self.user_confirmed(t):
            return False
        if _USER_REJECT_RE.search(t):
            return True
        return bool(
            re.search(r"\bno\b", t, re.I)
            and re.search(
                r"correcto|as[ií]|exacto|valido|v[aá]lido|es\s+eso|quiero|sirve",
                t,
                re.I,
            )
        )

    def user_accepts_proposal(self, text: str) -> bool:
        t = text.strip()
        if not t or self.user_rejects_proposal(t):
            return False
        if self.user_confirmed(t) or self.is_affirmative(t):
            return True
        return bool(_CONFIRMATION_INTENT_RE.search(t))

    def agent_asked_confirmation(self, messages: list[BaseMessage]) -> bool:
        agent = last_agent_message(messages) or ""
        return bool(_AGENT_ASKED_CONFIRM_RE.search(agent))

    def user_sent_tool_correction(self, text: str) -> bool:
        if not text.strip():
            return False
        if _USER_TOOL_CORRECTION_RE.search(text):
            return True
        return len(_FACTORY_NAME_RE.findall(text)) >= 2


class RequirementLifecycle:
    """Decides gathering vs complete and builds user-facing requirement messages."""

    def __init__(self, signals: ConversationSignals | None = None) -> None:
        self.signals = signals or ConversationSignals()

    def decide_status(
        self,
        req: MCPRequirement,
        llm_status: str,
        last_user_message: str,
        messages: list[BaseMessage] | None = None,
    ) -> str:
        if self.signals.user_rejects_proposal(last_user_message):
            return "gathering"
        if not req.is_ready():
            return "gathering"
        if self.signals.user_confirmed(last_user_message):
            return "complete"
        msgs = messages or []
        if (
            msgs
            and self.signals.agent_asked_confirmation(msgs)
            and self.signals.user_accepts_proposal(last_user_message)
        ):
            return "complete"
        return "gathering"

    def build_confirmation_message(self, req: MCPRequirement) -> str:
        lines = [
            "Con lo que contaste, propongo generar este MCP:",
            "",
            f"- **Nombre:** `{req.mcp_name}`",
            f"- **Descripción:** {req.description}",
        ]
        for t in req.tools:
            params = ", ".join(p.name for p in t.parameters) or "sin parámetros"
            lines.append(f"- **Tool** `{t.name}({params})`: {t.description}")
        if req.dependencies:
            lines.append(f"- **Dependencias:** {', '.join(req.dependencies)}")
        lines.append(f"- **Salida:** `{req.output_mode.value}`")
        lines.append("")
        lines.append(
            "¿Es correcto? Escribí **confirm** para generarlo o contame qué cambiar."
        )
        return "\n".join(lines)

    def user_facing_gaps(self, req: MCPRequirement) -> list[str]:
        if req.is_ready():
            return ["If the summary looks correct, type **confirm** to generate the MCP."]

        gaps: list[str] = []
        if not req.tools and not req.resources:
            gaps.append("Describe what the MCP should do (plain language is fine).")

        for note in req.clarifications_needed:
            text = note.strip()
            if text and not _AGENT_SIDE_CLARIFICATION_RE.search(text):
                gaps.append(text)

        if not gaps and not req.is_ready():
            gaps.append("Add a bit more context about what the MCP should do.")

        return gaps[:2]


_default_signals = ConversationSignals()
_default_lifecycle = RequirementLifecycle(_default_signals)
