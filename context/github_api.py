"""Shared GitHub API helpers for syncing docs and awesome lists."""
from __future__ import annotations

import re

import httpx

GITHUB_API = "https://api.github.com"
RAW_GITHUB = "https://raw.githubusercontent.com"

_CODE_EXTENSIONS = {".md", ".py", ".rst", ".txt"}


def _client(token: str | None, timeout: float = 90.0) -> httpx.Client:
    return httpx.Client(
        headers=github_headers(token),
        timeout=timeout,
        follow_redirects=True,
    )


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mcp-factory-context-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def normalize_github_token(raw: str | None) -> str | None:
    if not raw:
        return None
    token = raw.strip().strip('"').strip("'")
    if not token:
        return None
    if token.startswith(("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")):
        return token
    return None


def get_default_branch(client: httpx.Client, owner: str, repo: str) -> str:
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    response = client.get(url)
    if response.status_code == 401:
        raise PermissionError("GitHub API 401 — invalid GITHUB_TOKEN")
    if response.status_code == 404:
        raise FileNotFoundError(f"Repository not found: {owner}/{repo}")
    response.raise_for_status()
    return response.json().get("default_branch", "main")


def list_repo_files(
    client: httpx.Client,
    owner: str,
    repo: str,
    branch: str,
    *,
    prefix: str = "",
    extensions: set[str] | None = None,
    max_files: int = 30,
) -> list[str]:
    """List code/doc file paths under optional prefix."""
    exts = extensions or _CODE_EXTENSIONS
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    response = client.get(url)
    if response.status_code == 404:
        return ["README.md"]
    response.raise_for_status()
    data = response.json()

    paths: list[str] = []
    prefix_lower = prefix.lower().strip("/")

    for item in data.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if prefix_lower and not path.lower().startswith(prefix_lower):
            continue
        if not any(path.lower().endswith(ext) for ext in exts):
            continue
        # Skip noisy paths
        if any(x in path.lower() for x in ("/test/", "/tests/", "/__pycache__/", "/node_modules/")):
            continue
        paths.append(path)
        if len(paths) >= max_files:
            break

    if not paths and not prefix_lower:
        for fallback in ("README.md", "readme.md", "Readme.md"):
            paths.append(fallback)
    return paths[:max_files]


def download_raw(
    client: httpx.Client,
    owner: str,
    repo: str,
    branch: str,
    path: str,
    *,
    max_bytes: int = 512_000,
) -> bytes | None:
    url = f"{RAW_GITHUB}/{owner}/{repo}/{branch}/{path}"
    response = client.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    if len(response.content) > max_bytes:
        return None
    return response.content


def parse_github_repo(slug: str) -> tuple[str, str]:
    slug = slug.strip().strip("/")
    if slug.startswith("https://github.com/"):
        slug = slug.replace("https://github.com/", "")
    parts = slug.split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid repo slug: {slug}")
    return parts[0], parts[1]
