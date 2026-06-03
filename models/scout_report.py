"""Models for scout (relevador) agents and validated research."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScoutedFile(BaseModel):
    repo: str
    path: str
    content: str
    local_path: str = ""


class ScoutedRepo(BaseModel):
    slug: str
    reason: str
    files_fetched: int = 0


class ScoutReport(BaseModel):
    profile: str
    agent_name: str
    repos: list[ScoutedRepo] = Field(default_factory=list)
    files: list[ScoutedFile] = Field(default_factory=list)
    status: str = "ok"  # ok | partial | failed
    errors: list[str] = Field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)


class ValidatedResearch(BaseModel):
    is_valid: bool
    total_files: int
    total_repos: int
    context_markdown: str
    scout_summaries: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rejected_files: list[str] = Field(default_factory=list)
    persisted_paths: list[str] = Field(default_factory=list)
    feedback_sections: list[str] = Field(default_factory=list)
