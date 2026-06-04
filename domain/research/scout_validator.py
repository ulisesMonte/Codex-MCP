"""Validate and merge parallel scout research reports."""
from __future__ import annotations

import re

from models.scout_report import ScoutReport, ValidatedResearch


class ScoutResearchValidator:
    """Aggregates scout reports into ValidatedResearch for the design phase."""

    PLACEHOLDER_RE = re.compile(
        r"generated successfully|not implemented|stub|todo: implement",
        re.I,
    )
    AWESOME_PROFILES = frozenset({"mcp", "api", "data"})

    def dedupe_by_profile(self, reports: list[ScoutReport]) -> list[ScoutReport]:
        by_profile: dict[str, ScoutReport] = {}
        for report in reports:
            by_profile[report.profile] = report
        return list(by_profile.values())

    def validate(self, reports: list[ScoutReport]) -> ValidatedResearch:
        warnings: list[str] = []
        rejected: list[str] = []
        summaries: list[str] = []
        accepted_files: list[tuple[str, str, str, str]] = []

        by_profile = {r.profile: r for r in reports}
        ok_scouts = sum(1 for r in reports if r.status == "ok")
        partial_scouts = sum(1 for r in reports if r.status == "partial")

        if len(reports) < 4:
            warnings.append(f"Expected 4 scout reports (mcp/api/data/docs), got {len(reports)}")

        for report in reports:
            summaries.append(
                f"- **{report.agent_name}** ({report.profile}): "
                f"{report.file_count} files, status={report.status}"
            )
            if report.errors:
                warnings.extend(f"{report.agent_name}: {e}" for e in report.errors[:2])

            min_files = 1 if report.profile == "docs" else 2
            useful = 0
            for f in report.files:
                if report.profile != "docs" and self.PLACEHOLDER_RE.search(f.content[:500]):
                    rejected.append(f"{f.repo}:{f.path} (placeholder content)")
                    continue
                if len(f.content.strip()) < 60:
                    rejected.append(f"{f.repo}:{f.path} (too short)")
                    continue
                accepted_files.append((f.repo, f.path, f.content, report.profile))
                useful += 1

            if useful < min_files:
                warnings.append(
                    f"{report.agent_name}: only {useful} useful files (expected >= {min_files})"
                )

        docs_report = by_profile.get("docs")
        has_generated_brief = bool(
            docs_report and any(f.repo == "generated" for f in docs_report.files)
        )
        if docs_report and not has_generated_brief:
            warnings.append("docs scout: missing generated research_brief.md")

        awesome_files = [f for f in accepted_files if f[3] in self.AWESOME_PROFILES]
        total_files = len(accepted_files)
        repos = {
            r
            for r, _, _, p in accepted_files
            if p in self.AWESOME_PROFILES and r not in ("local", "generated")
        }

        is_valid = (
            total_files >= 5
            and ok_scouts >= 2
            and has_generated_brief
            and len(awesome_files) >= 3
        )
        if (
            not is_valid
            and total_files >= 3
            and has_generated_brief
            and (ok_scouts + partial_scouts) >= 3
        ):
            is_valid = True
            warnings.append("Accepted with partial scout coverage")

        markdown = self._build_context_markdown(summaries, accepted_files, warnings)

        return ValidatedResearch(
            is_valid=is_valid,
            total_files=total_files,
            total_repos=len(repos),
            context_markdown=markdown,
            scout_summaries=summaries,
            warnings=warnings,
            rejected_files=rejected,
        )

    def _build_context_markdown(
        self,
        summaries: list[str],
        files: list[tuple[str, str, str, str]],
        warnings: list[str],
    ) -> str:
        parts = [
            "## Validated research from scout agents (use for implementation)\n",
            "### Scout summary\n",
            *summaries,
            "",
        ]
        if warnings:
            parts.append("### Warnings\n")
            parts.extend(f"- {w}" for w in warnings[:5])
            parts.append("")

        generated = [f for f in files if f[0] == "generated"]
        local = [f for f in files if f[0] == "local"]
        github = [f for f in files if f[0] not in ("generated", "local")]

        if generated:
            parts.append("### Generated research brief\n")
            for _, path, content, _ in generated:
                parts.append(f"#### `{path}`\n")
                parts.append(f"```markdown\n{content[:5000]}\n```\n")

        if local:
            parts.append("### Local knowledge excerpts\n")
            for _, path, content, _ in local[:4]:
                parts.append(f"#### `{path}`\n")
                parts.append(f"```\n{content[:3000]}\n```\n")

        if github:
            parts.append("### Fetched from GitHub (awesome → repos)\n")
            for repo, path, content, _ in github[:10]:
                parts.append(f"#### `{repo}` — `{path}`\n")
                parts.append(f"```\n{content[:3500]}\n```\n")

        return "\n".join(parts)


_default_scout_validator = ScoutResearchValidator()


def validate_reports(reports: list[ScoutReport]) -> ValidatedResearch:
    return _default_scout_validator.validate(reports)
