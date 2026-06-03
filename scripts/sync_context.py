"""Orchestrate Option C context sync: tech docs (codegen) + awesome discovery."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _run(script: str, args: list[str]) -> int:
    cmd = [sys.executable, str(_ROOT / "scripts" / script), *args]
    print(f"\n>> {' '.join(cmd)}")
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Option C: sync tech docs for codegen + awesome discovery index.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-awesome", action="store_true", help="Skip awesome discovery step")
    parser.add_argument("--skip-docs", action="store_true", help="Skip tech docs sync")
    parser.add_argument("--preset-tech", action="store_true", help="Sync awesome with --preset tech first")
    args = parser.parse_args()

    dry = ["--dry-run"] if args.dry_run else []
    code = 0

    if not args.skip_docs:
        code = _run("sync_tech_docs.py", dry)
        if code != 0:
            return code

    if not args.skip_awesome:
        if args.preset_tech:
            code = _run("sync_awesome_md.py", ["--preset", "tech", *dry])
            if code != 0 and not args.dry_run:
                print("Warning: awesome sync had errors; continuing with discovery anyway.")
        code = _run("build_discovery_index.py", [])
        if code != 0:
            return code

    print("\nOption C sync complete.")
    print("  Codegen RAG: context/docs/ + context/knowledge/*.md + generated/mcps/")
    print("  Discovery:   context/discovery/ecosystem.json (names only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
