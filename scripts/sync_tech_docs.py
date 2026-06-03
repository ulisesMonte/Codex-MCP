"""Sync curated technical docs + code into context/docs/ for codegen RAG (Option C)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx

from config.paths import context_docs_dir
from context.github_api import (
    _client,
    download_raw,
    get_default_branch,
    list_repo_files,
    normalize_github_token,
    parse_github_repo,
)

CATALOG_PATH = Path(__file__).parent / "tech_docs_catalog.json"


def load_catalog() -> list[dict]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return data.get("sources", [])


def sync_source(
    source: dict,
    output_dir: Path,
    token: str | None,
    dry_run: bool = False,
) -> tuple[int, str | None]:
    owner, repo = parse_github_repo(source["repo"])
    source_id = source["id"]
    dest = output_dir / source_id
    prefixes = source.get("prefixes", [""])
    max_files = int(source.get("max_files", 20))
    per_prefix = max(3, max_files // max(len(prefixes), 1))

    saved = 0

    with _client(token) as client:
        try:
            branch = get_default_branch(client, owner, repo)
        except Exception as exc:
            return 0, str(exc)

        all_paths: list[str] = []
        seen: set[str] = set()
        for prefix in prefixes:
            for path in list_repo_files(
                client, owner, repo, branch,
                prefix=prefix,
                max_files=per_prefix,
            ):
                if path not in seen:
                    seen.add(path)
                    all_paths.append(path)
            if len(all_paths) >= max_files:
                break
        all_paths = all_paths[:max_files]

        if dry_run:
            return len(all_paths), None

        dest.mkdir(parents=True, exist_ok=True)
        for path in all_paths:
            content = download_raw(client, owner, repo, branch, path)
            if not content:
                continue
            safe_name = path.replace("/", "__")
            (dest / safe_name).write_bytes(content)
            saved += 1

        meta = {
            "id": source_id,
            "repo": source["repo"],
            "branch": branch,
            "tags": source.get("tags", []),
            "files": saved,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        (dest / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return saved, None


def sync_all(
    *,
    output_dir: Path | None = None,
    token: str | None = None,
    source_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    out = output_dir or context_docs_dir()
    catalog = load_catalog()
    if source_ids:
        catalog = [s for s in catalog if s["id"] in source_ids]

    results = {"ok": 0, "failed": 0, "files": 0, "errors": []}
    for source in catalog:
        saved, err = sync_source(source, out, token, dry_run=dry_run)
        if err:
            results["failed"] += 1
            results["errors"].append(f"{source['id']}: {err}")
        else:
            results["ok"] += 1
            results["files"] += saved
            action = "would fetch" if dry_run else "saved"
            print(f"  [{source['id']}] {action} {saved} files from {source['repo']}")

    if not dry_run:
        manifest = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sources": [s["id"] for s in catalog],
            **results,
        }
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download curated technical docs/code for MCP codegen RAG.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--source", action="append", dest="sources", help="Sync only this catalog id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="List catalog sources")
    args = parser.parse_args(argv)

    if args.list:
        for s in load_catalog():
            tags = ", ".join(s.get("tags", []))
            print(f"  {s['id']:20} {s['repo']:40} [{tags}]")
        return 0

    import os

    raw = args.token or os.getenv("GITHUB_TOKEN")
    token = normalize_github_token(raw)
    out = args.output or context_docs_dir()

    print(f"Tech docs sync -> {out}")
    if raw and not token:
        print("Warning: invalid GITHUB_TOKEN format — using unauthenticated API.")
    elif token:
        print("Using GITHUB_TOKEN.")

    results = sync_all(
        output_dir=out,
        token=token,
        source_ids=args.sources,
        dry_run=args.dry_run,
    )

    label = "found" if args.dry_run else "saved"
    print(
        f"\nDone: {results['ok']} sources OK, {results['files']} files {label}, "
        f"{results['failed']} failed."
    )
    for err in results["errors"][:5]:
        print(f"  - {err}")
    return 1 if results["failed"] and results["ok"] == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
