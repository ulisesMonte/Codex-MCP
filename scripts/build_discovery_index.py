"""Build discovery-only index from awesome lists (links/deps, not codegen RAG)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.paths import awesome_knowledge_dir, context_discovery_dir

_GITHUB_RE = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.I,
)
_PYPI_RE = re.compile(r"https://pypi\.org/project/([A-Za-z0-9_.-]+)", re.I)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_BULLET_RE = re.compile(r"^\s*[-*]\s+\[?([^\]]+)\]?\(?", re.M)


def extract_from_markdown(text: str) -> dict:
    github_repos: set[str] = set()
    pypi_packages: set[str] = set()
    labels: set[str] = set()

    for owner, repo in _GITHUB_RE.findall(text):
        if owner.lower() in {"sponsors", "apps", "marketplace", "topics"}:
            continue
        github_repos.add(f"{owner}/{repo}")

    for pkg in _PYPI_RE.findall(text):
        pypi_packages.add(pkg.lower().replace("_", "-"))

    for label, url in _LINK_RE.findall(text):
        label = label.strip()
        if 2 < len(label) < 80:
            labels.add(label)

    return {
        "github_repos": sorted(github_repos),
        "pypi_packages": sorted(pypi_packages),
        "labels": sorted(labels)[:200],
    }


def build_index(awesome_dir: Path) -> dict:
    aggregated: dict = {
        "github_repos": set(),
        "pypi_packages": set(),
        "labels": set(),
        "source_lists": [],
    }

    if not awesome_dir.exists():
        return {"error": f"Awesome dir not found: {awesome_dir}", "github_repos": [], "pypi_packages": []}

    for list_dir in sorted(awesome_dir.iterdir()):
        if not list_dir.is_dir() or list_dir.name == "manifest.json":
            continue
        list_name = list_dir.name
        list_data = {"list": list_name, "github_repos": set(), "pypi_packages": set()}

        for md_path in list_dir.rglob("*.md"):
            try:
                text = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parsed = extract_from_markdown(text)
            list_data["github_repos"].update(parsed["github_repos"])
            list_data["pypi_packages"].update(parsed["pypi_packages"])
            aggregated["github_repos"].update(parsed["github_repos"])
            aggregated["pypi_packages"].update(parsed["pypi_packages"])
            aggregated["labels"].update(parsed["labels"])

        if list_data["github_repos"] or list_data["pypi_packages"]:
            aggregated["source_lists"].append({
                "list": list_name,
                "github_repos_count": len(list_data["github_repos"]),
                "pypi_packages_count": len(list_data["pypi_packages"]),
            })

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "discovery-only — use for deps/names, not codegen bodies",
        "github_repos": sorted(aggregated["github_repos"]),
        "pypi_packages": sorted(aggregated["pypi_packages"]),
        "labels_sample": sorted(aggregated["labels"])[:500],
        "source_lists": aggregated["source_lists"],
        "stats": {
            "github_repos": len(aggregated["github_repos"]),
            "pypi_packages": len(aggregated["pypi_packages"]),
            "awesome_lists": len(aggregated["source_lists"]),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build discovery index from synced awesome lists.")
    parser.add_argument("--awesome-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    awesome_dir = args.awesome_dir or awesome_knowledge_dir()
    out_dir = args.output or context_discovery_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    index = build_index(awesome_dir)
    out_path = out_dir / "ecosystem.json"
    out_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    stats = index.get("stats", {})
    print(f"Discovery index -> {out_path}")
    print(
        f"  {stats.get('awesome_lists', 0)} awesome lists, "
        f"{stats.get('github_repos', 0)} github repos, "
        f"{stats.get('pypi_packages', 0)} pypi packages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
