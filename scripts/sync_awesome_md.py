"""Download markdown files from Awesome List repos for RAG knowledge."""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx

from config.paths import awesome_knowledge_dir

AWESOME_INDEX_URL = (
    "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md"
)
GITHUB_API = "https://api.github.com"
RAW_GITHUB = "https://raw.githubusercontent.com"

# github.com/owner/repo with optional /tree/branch or #readme
_REPO_LINK_RE = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:/tree/[^/\s)]+)?(?:#readme)?",
    re.IGNORECASE,
)

MAX_FILE_BYTES = 512_000
DEFAULT_WORKERS = 4

# GitHub paths that look like owner/repo but are not cloneable repositories.
_SKIP_GITHUB_OWNERS = frozenset({
    "sponsors",
    "apps",
    "marketplace",
    "features",
    "login",
    "settings",
    "organizations",
    "topics",
    "collections",
    "trending",
    "explore",
    "github",
})


@dataclass
class RepoRef:
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def dir_name(self) -> str:
        return f"{self.owner}_{self.repo}".lower()


@dataclass
class SyncStats:
    repos_total: int = 0
    repos_ok: int = 0
    repos_failed: int = 0
    repos_skipped: int = 0
    files_saved: int = 0
    files_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def is_valid_awesome_repo(ref: RepoRef) -> bool:
    """Ignore github.com/sponsors/..., marketplace, etc."""
    return ref.owner.lower() not in _SKIP_GITHUB_OWNERS


def parse_awesome_repos(readme_text: str) -> list[RepoRef]:
    """Extract unique GitHub repos linked from the awesome index readme."""
    seen: set[str] = set()
    repos: list[RepoRef] = []
    for owner, repo in _REPO_LINK_RE.findall(readme_text):
        repo = repo.strip("/")
        ref = RepoRef(owner=owner, repo=repo)
        if not is_valid_awesome_repo(ref):
            continue
        key = ref.slug.lower()
        if key in seen:
            continue
        seen.add(key)
        repos.append(ref)
    return repos


def filter_repos(repos: list[RepoRef], pattern: str | None) -> list[RepoRef]:
    if not pattern:
        return repos
    needle = pattern.lower()
    return [r for r in repos if needle in r.slug.lower()]


# Curated keywords for MCP / backend / codegen RAG (matches owner/repo slug).
TECH_PRESET: dict[str, list[str]] = {
    "mcp-ai": [
        "mcp", "llm", "langchain", "openai", "copilot-agent", "nlg", "genkit",
        "prompt", "rag", "vector", "embedding", "machine-learning", "deep-learning",
        "data-science", "nlp", "chatbot", "agent",
    ],
    "python": [
        "python", "asyncio", "fastapi", "django", "flask", "sqlalchemy", "typing",
        "pydantic", "pytest", "pip", "pypi", "celery", "micropython",
    ],
    "api-backend": [
        "rest", "graphql", "grpc", "microservice", "integration", "webhook",
        "openapi", "swagger", "backend", "serverless", "fastapi", "node-red",
    ],
    "databases": [
        "postgres", "mysql", "mongo", "redis", "sqlite", "bigquery", "database",
        "sql", "hadoop", "prisma", "elastic", "cassandra", "neo4j",
    ],
    "cloud-devops": [
        "aws", "google-cloud", "azure", "docker", "kubernetes", "terraform",
        "cloudflare", "firebase", "heroku", "digitalocean", "devops", "ci-cd",
        "github-action", "ansible",
    ],
    "auth-security": [
        "oauth", "openid", "appsec", "security", "jwt", "auth", "cryptography",
        "pentest", "devsecops",
    ],
    "languages": [
        "javascript", "typescript", "nodejs", "go", "rust", "java", "kotlin",
        "dotnet", "php", "ruby", "elixir", "scala",
    ],
    "testing": [
        "testing", "test", "tdd", "bdd", "mock", "selenium", "playwright",
    ],
    "data-messaging": [
        "kafka", "rabbit", "mqtt", "websocket", "csv", "json", "yaml", "etl",
    ],
    "tools-cli": [
        "cli", "devtools", "automation", "scrap", "http", "curl", "git",
    ],
}

# Union of all tech presets — use with: --preset tech
TECH_ALL_TERMS: list[str] = sorted({t for terms in TECH_PRESET.values() for t in terms})


def filter_repos_by_preset(repos: list[RepoRef], preset: str) -> list[RepoRef]:
    """Filter repos by a named preset or 'tech' (all technical terms)."""
    key = preset.lower().strip()
    if key == "tech":
        terms = TECH_ALL_TERMS
    elif key in TECH_PRESET:
        terms = TECH_PRESET[key]
    else:
        available = ["tech", *sorted(TECH_PRESET)]
        raise ValueError(f"Unknown preset {preset!r}. Available: {', '.join(available)}")

    seen: set[str] = set()
    matched: list[RepoRef] = []
    for ref in repos:
        slug = ref.slug.lower()
        if any(term in slug for term in terms):
            if ref.slug not in seen:
                seen.add(ref.slug)
                matched.append(ref)
    return matched


def list_presets() -> str:
    lines = ["Available --preset values:", "", "  tech  — all categories below (recommended for MCP RAG)", ""]
    for name, terms in TECH_PRESET.items():
        lines.append(f"  {name} ({len(terms)} keywords)")
        lines.append(f"    e.g. matches slugs containing: {', '.join(terms[:8])}...")
        lines.append("")
    lines.append("Single-keyword --filter examples:")
    lines.append("  python, mcp, fastapi, postgres, docker, graphql, microservice, rest, oauth")
    return "\n".join(lines)


def fetch_text(client: httpx.Client, url: str) -> str:
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.text


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mcp-factory-awesome-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        # GitHub accepts both Bearer and token schemes for PATs.
        headers["Authorization"] = f"Bearer {token}"
    return headers


def normalize_github_token(raw: str | None) -> str | None:
    """Return a trimmed PAT or None if missing / invalid format."""
    if not raw:
        return None
    token = raw.strip().strip('"').strip("'")
    if not token:
        return None
    if token.startswith(("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")):
        return token
    return None


def get_default_branch(client: httpx.Client, ref: RepoRef) -> str:
    url = f"{GITHUB_API}/repos/{ref.owner}/{ref.repo}"
    response = client.get(url)
    if response.status_code == 401:
        raise PermissionError(
            "GitHub API 401 Unauthorized — invalid or expired GITHUB_TOKEN. "
            "Remove it with: Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue "
            "or create a new PAT (scope public_repo)."
        )
    if response.status_code == 404:
        raise FileNotFoundError(f"Repository not found: {ref.slug}")
    response.raise_for_status()
    return response.json().get("default_branch", "main")


def list_markdown_paths(client: httpx.Client, ref: RepoRef, branch: str) -> list[str]:
    """List .md blob paths via Git Trees API (recursive)."""
    url = f"{GITHUB_API}/repos/{ref.owner}/{ref.repo}/git/trees/{branch}?recursive=1"
    response = client.get(url)
    if response.status_code == 404:
        # Empty repo or missing branch — fallback to readme only
        return ["readme.md"]
    response.raise_for_status()
    data = response.json()
    if data.get("truncated"):
        # Very large repo: prefer root-level md files only
        return _list_root_markdown(client, ref, branch)

    paths: list[str] = []
    for item in data.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if path.lower().endswith(".md"):
            paths.append(path)
    return paths or ["readme.md"]


def _list_root_markdown(client: httpx.Client, ref: RepoRef, branch: str) -> list[str]:
    url = f"{GITHUB_API}/repos/{ref.owner}/{ref.repo}/contents"
    response = client.get(url, params={"ref": branch})
    if response.status_code != 200:
        return ["readme.md"]
    paths = []
    for item in response.json():
        if isinstance(item, dict) and item.get("name", "").lower().endswith(".md"):
            paths.append(item["name"])
    return paths or ["readme.md"]


def download_markdown(
    client: httpx.Client,
    ref: RepoRef,
    branch: str,
    path: str,
) -> bytes | None:
    url = f"{RAW_GITHUB}/{ref.owner}/{ref.repo}/{branch}/{path}"
    response = client.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    content = response.content
    if len(content) > MAX_FILE_BYTES:
        return None
    return content


def sync_repo(
    ref: RepoRef,
    output_dir: Path,
    token: str | None,
    dry_run: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[int, int, str | None]:
    """Download all markdown files for one repo. Returns (saved, skipped, error)."""
    headers = github_headers(token)
    repo_dir = output_dir / ref.dir_name
    saved = 0
    skipped = 0

    with httpx.Client(headers=headers, timeout=60.0) as client:
        try:
            branch = get_default_branch(client, ref)
            md_paths = list_markdown_paths(client, ref, branch)
        except Exception as exc:
            return 0, 0, str(exc)

        if dry_run:
            return len(md_paths), 0, None

        repo_dir.mkdir(parents=True, exist_ok=True)
        for path in md_paths:
            try:
                content = download_markdown(client, ref, branch, path)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    return saved, skipped, "GitHub API rate limit — set GITHUB_TOKEN"
                skipped += 1
                continue

            if content is None:
                skipped += 1
                continue

            safe_name = path.replace("/", "__")
            target = repo_dir / safe_name
            target.write_bytes(content)
            saved += 1
            if on_progress:
                on_progress(f"{ref.slug} -> {path}")

    meta = {
        "owner": ref.owner,
        "repo": ref.repo,
        "branch": branch,
        "files": len(md_paths),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    (repo_dir / "_meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
    return saved, skipped, None


def load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def sync_all_awesome_md(
    *,
    index_url: str = AWESOME_INDEX_URL,
    output_dir: Path | None = None,
    token: str | None = None,
    limit: int | None = None,
    filter_text: str | None = None,
    preset: str | None = None,
    workers: int = DEFAULT_WORKERS,
    dry_run: bool = False,
    resume: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> SyncStats:
    out = output_dir or awesome_knowledge_dir()
    stats = SyncStats()

    with httpx.Client(timeout=60.0) as client:
        readme = fetch_text(client, index_url)

    repos = parse_awesome_repos(readme)
    if preset:
        repos = filter_repos_by_preset(repos, preset)
    else:
        repos = filter_repos(repos, filter_text)
    stats.repos_total = len(repos)
    if limit:
        repos = repos[:limit]

    manifest_path = out / "manifest.json"
    manifest = load_manifest(manifest_path) if resume else {}
    completed = set(manifest.get("completed_repos", []))

    pending = [r for r in repos if r.slug not in completed] if resume else repos

    def _run_one(ref: RepoRef) -> tuple[RepoRef, int, int, str | None]:
        saved, skipped, err = sync_repo(ref, out, token, dry_run=dry_run, on_progress=on_progress)
        return ref, saved, skipped, err

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_run_one, ref): ref for ref in pending}
        for future in as_completed(futures):
            ref, saved, skipped, err = future.result()
            stats.files_saved += saved
            stats.files_skipped += skipped
            if err:
                stats.repos_failed += 1
                stats.errors.append(f"{ref.slug}: {err}")
            else:
                stats.repos_ok += 1
                if not dry_run:
                    completed.add(ref.slug)

    if not dry_run:
        manifest.update(
            {
                "index_url": index_url,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed_repos": sorted(completed),
                "repos_total": stats.repos_total,
                "repos_ok": stats.repos_ok,
                "repos_failed": stats.repos_failed,
                "files_saved": stats.files_saved,
            }
        )
        save_manifest(manifest_path, manifest)

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download all .md files from Awesome List GitHub repos.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: context/knowledge/awesome)",
    )
    parser.add_argument(
        "--index-url",
        default=AWESOME_INDEX_URL,
        help="Awesome index readme URL",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of repos to process (useful for testing)",
    )
    parser.add_argument(
        "--filter",
        dest="filter_text",
        default=None,
        help="Only repos whose slug contains this text (e.g. python, mcp)",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help="Use a curated filter preset: tech, mcp-ai, python, api-backend, databases, ...",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="Show all --preset options and exit",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Parallel repo downloads",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List repos and md counts without downloading",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-download all repos even if already in manifest",
    )
    args = parser.parse_args(argv)

    if args.list_presets:
        print(list_presets())
        return 0

    if args.preset and args.filter_text:
        print("Error: use --preset OR --filter, not both.")
        return 1

    import os

    raw_token = args.token or os.getenv("GITHUB_TOKEN")
    token = normalize_github_token(raw_token)
    out = args.output or awesome_knowledge_dir()

    print(f"Awesome sync -> {out}")
    if args.preset:
        print(f"Preset: {args.preset}")
    if raw_token and not token:
        print(
            "Warning: GITHUB_TOKEN is set but invalid (must start with ghp_ or github_pat_).\n"
            "  Clear it: Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue\n"
            "  Or create a new token: GitHub -> Settings -> Developer settings -> PAT"
        )
    elif token:
        print("Using GITHUB_TOKEN (authenticated API).")
    else:
        print("No token — public API only (60 requests/hour). Set GITHUB_TOKEN for 5000/h.")

    def progress(msg: str) -> None:
        print(f"  {msg}")

    stats = sync_all_awesome_md(
        index_url=args.index_url,
        output_dir=out,
        token=token,
        limit=args.limit,
        filter_text=args.filter_text,
        preset=args.preset,
        workers=args.workers,
        dry_run=args.dry_run,
        resume=not args.no_resume,
        on_progress=progress if not args.dry_run else None,
    )

    print(
        f"\nDone: {stats.repos_ok}/{stats.repos_total} repos"
        + (f", {stats.repos_skipped} non-repo links skipped" if stats.repos_skipped else "")
        + f", {stats.files_saved} files {'found' if args.dry_run else 'saved'}"
        + f", {stats.files_skipped} skipped, {stats.repos_failed} failed."
    )
    if stats.errors:
        print("Errors (first 10):")
        for line in stats.errors[:10]:
            print(f"  - {line}")

    return 1 if stats.repos_failed and stats.repos_ok == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
