#!/usr/bin/env python3
"""Fetch pinned SOURCE REFERENCE checkouts (NOT vendored dependencies).

Usage:
  python3 tools/fetch_reference_sources.py --list
  python3 tools/fetch_reference_sources.py --only forgetty,kwi
  python3 tools/fetch_reference_sources.py
"""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))


def call(*args):
    print("+", *map(str, args), flush=True)
    subprocess.run(args, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="Show pinned SHAs without downloading")
    p.add_argument("--only", help="Comma-separated source slugs, e.g. forgetty,kwi")
    args = p.parse_args()
    allowed = set(args.only.split(",")) if args.only else None
    selected = [x for x in LOCK["references"] if allowed is None or x["slug"] in allowed]
    if not selected or (allowed is not None and allowed - {x["slug"] for x in selected}):
        p.error("Unknown or empty --only source slug")
    dest = ROOT / "references"
    if not args.list:
        dest.mkdir(exist_ok=True)
    for ref in selected:
        name, commit = ref["slug"], ref["commit"]
        path = dest / name
        print(f"{name}: {commit} ({ref['license']})")
        if args.list:
            continue
        if not (path / ".git").is_dir():
            call("git", "clone", "--filter=blob:none", "--no-checkout", "https://github.com/" + ref["repo"] + ".git", str(path))
        # fetch the pinned object, which may no longer be the default HEAD
        call("git", "-C", str(path), "fetch", "--depth=1", "origin", commit)
        call("git", "-C", str(path), "checkout", "--detach", commit)
        actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if actual != commit:
            raise SystemExit(f"PIN MISMATCH for {name}: {actual} != {commit}")


if __name__ == "__main__":
    main()
