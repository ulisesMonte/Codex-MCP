"""Fetch code snippets from GitHub repos discovered via awesome / requirement."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx

from config.paths import (
    awesome_knowledge_dir,
    context_discovery_dir,
    context_scouted_dir,
)
from context.github_api import (
    _client,
    download_raw,
    get_default_branch,
    list_repo_files,
    normalize_github_token,
    parse_github_repo,
)
from models.mcp_requirement import MCPRequirement
from models.scout_report import ScoutedFile, ScoutedRepo, ScoutReport

_GITHUB_LINK_RE = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.I,
)

_SKIP_OWNERS = frozenset({"sponsors", "apps", "marketplace", "topics", "github"})

SCOUT_PROFILES: dict[str, dict] = {
    "mcp": {
        "agent_name": "scout_mcp_agent",
        "keywords": [
            "mcp", "fastmcp", "modelcontextprotocol", "tool", "stdio", "protocol", "agent",
        ],
        "seed_repos": [
            "jlowin/fastmcp",
            "modelcontextprotocol/python-sdk",
        ],
    },
    "api": {
        "agent_name": "scout_api_agent",
        "keywords": [
            "api", "rest", "fastapi", "graphql", "httpx", "microservice",
            "controller", "service", "webhook", "openapi",
        ],
        "seed_repos": [
            "fastapi/fastapi",
            "encode/httpx",
            "mfornos/awesome-microservices",
        ],
    },
    "data": {
        "agent_name": "scout_data_agent",
        "keywords": [
            "postgres", "postgresql", "mysql", "mongo", "redis", "bigquery",
            "database", "connection", "sql", "sqlalchemy", "psycopg",
        ],
        "seed_repos": [
            "psycopg/psycopg",
            "googleapis/python-bigquery",
            "mongodb/mongo-python-driver",
        ],
    },
}

DEPENDENCY_REPO_HINTS: dict[str, str] = {
    "google-cloud-bigquery": "googleapis/python-bigquery",
    "psycopg2-binary": "psycopg/psycopg",
    "psycopg2": "psycopg/psycopg",
    "pymongo": "mongodb/mongo-python-driver",
    "redis": "redis/redis-py",
    "httpx": "encode/httpx",
    "fastapi": "fastapi/fastapi",
    "sqlalchemy": "sqlalchemy/sqlalchemy",
}


def run_scout(
    profile: str,
    requirement: MCPRequirement,
    session_id: str,
    *,
    max_repos: int = 2,
    files_per_repo: int = 3,
) -> ScoutReport:
    """Discover repos and download 2-3 code/doc files per repo."""
    cfg = SCOUT_PROFILES[profile]
    token = normalize_github_token(os.getenv("GITHUB_TOKEN"))
    keywords = _build_keywords(requirement, cfg["keywords"])

    candidates = _rank_repos(keywords, requirement)
    for seed in cfg.get("seed_repos", []):
        if seed not in candidates:
            candidates.insert(0, seed)

    report = ScoutReport(
        profile=profile,
        agent_name=cfg["agent_name"],
    )
    out_dir = context_scouted_dir() / session_id / profile
    out_dir.mkdir(parents=True, exist_ok=True)

    if not candidates:
        report.status = "failed"
        report.errors.append("No matching repos found in discovery/awesome index")
        return report

    try:
        with _client(token) as client:
            for slug in candidates[:max_repos]:
                try:
                    owner, repo = parse_github_repo(slug)
                    branch = get_default_branch(client, owner, repo)
                    paths = _pick_files(
                        client, owner, repo, branch, keywords, files_per_repo
                    )
                    fetched = 0
                    for path in paths:
                        raw = download_raw(client, owner, repo, branch, path, max_bytes=80_000)
                        if not raw:
                            continue
                        text = raw.decode("utf-8", errors="replace")
                        if len(text.strip()) < 40:
                            continue
                        local = out_dir / f"{repo}__{path.replace('/', '__')}"
                        local.write_text(text, encoding="utf-8")
                        report.files.append(
                            ScoutedFile(
                                repo=slug,
                                path=path,
                                content=text[:6000],
                                local_path=str(local),
                            )
                        )
                        fetched += 1
                    report.repos.append(
                        ScoutedRepo(
                            slug=slug,
                            reason=f"matched keywords: {', '.join(keywords[:5])}",
                            files_fetched=fetched,
                        )
                    )
                except Exception as exc:
                    report.errors.append(f"{slug}: {exc}")
    except Exception as exc:
        report.errors.append(str(exc))

    if report.file_count >= 2:
        report.status = "ok"
    elif report.file_count >= 1:
        report.status = "partial"
    else:
        report.status = "failed"

    meta = report.model_dump()
    (out_dir / "_report.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return report


def _build_keywords(requirement: MCPRequirement, profile_keywords: list[str]) -> list[str]:
    words: set[str] = set(profile_keywords)
    words.update(requirement.mcp_name.lower().split("_"))
    for tool in requirement.tools:
        words.update(tool.name.lower().split("_"))
        words.update(tool.description.lower().split())
    words.update(requirement.description.lower().split())
    for dep in requirement.dependencies:
        words.add(dep.lower().split("[")[0])
    return [w for w in words if len(w) >= 3][:30]


def _rank_repos(keywords: list[str], requirement: MCPRequirement) -> list[str]:
    scored: dict[str, int] = {}

    for dep in requirement.dependencies:
        hint = DEPENDENCY_REPO_HINTS.get(dep.lower().split("[")[0])
        if hint:
            scored[hint] = scored.get(hint, 0) + 10

    eco_path = context_discovery_dir() / "ecosystem.json"
    if eco_path.exists():
        try:
            eco = json.loads(eco_path.read_text(encoding="utf-8"))
            for slug in eco.get("github_repos", []):
                score = _score_slug(slug, keywords)
                if score:
                    scored[slug] = scored.get(slug, 0) + score
        except json.JSONDecodeError:
            pass

    awesome_dir = awesome_knowledge_dir()
    if awesome_dir.exists():
        for list_dir in awesome_dir.iterdir():
            if not list_dir.is_dir():
                continue
            list_name = list_dir.name.lower()
            list_boost = sum(1 for k in keywords if k in list_name)
            for md_path in list_dir.glob("*.md"):
                try:
                    text = md_path.read_text(encoding="utf-8", errors="replace")[:50_000]
                except OSError:
                    continue
                for owner, repo in _GITHUB_LINK_RE.findall(text):
                    if owner.lower() in _SKIP_OWNERS:
                        continue
                    slug = f"{owner}/{repo}"
                    score = _score_slug(slug, keywords) + list_boost
                    if score:
                        scored[slug] = scored.get(slug, 0) + score

    ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    return [slug for slug, _ in ranked if not slug.lower().startswith("sindresorhus/awesome")]


def _score_slug(slug: str, keywords: list[str]) -> int:
    lower = slug.lower()
    return sum(2 for k in keywords if k in lower)


def _pick_files(
    client: httpx.Client,
    owner: str,
    repo: str,
    branch: str,
    keywords: list[str],
    limit: int,
) -> list[str]:
    all_paths = list_repo_files(client, owner, repo, branch, max_files=40)
    if not all_paths:
        return ["README.md"]

    def score(path: str) -> int:
        p = path.lower()
        s = 0
        if p.endswith(".py"):
            s += 3
        if p.endswith(".md"):
            s += 2
        if "example" in p or "sample" in p:
            s += 2
        if "readme" in p:
            s += 4
        for k in keywords:
            if k in p:
                s += 1
        if "/test" in p:
            s -= 2
        return s

    ranked = sorted(all_paths, key=score, reverse=True)
    chosen: list[str] = []
    for path in ranked:
        if path not in chosen:
            chosen.append(path)
        if len(chosen) >= limit:
            break
    return chosen[:limit]
