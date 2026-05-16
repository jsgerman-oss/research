#!/usr/bin/env python3
"""
clone-corpus.py — clone Go-language corpus repos for OQ-AST-1 §6.3.

Phase 1a: Go-only. Python / JS / TS entries are logged and skipped.

Special case: jsgerman-oss/blackrim.dev@HEAD is the live Blackrim repo;
instead of cloning, we symlink (or reuse) /Users/jayse/Code/blackrim directly.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORPUS_FILE = Path(__file__).parent / "corpus.txt"
SCRATCH_DIR = Path(__file__).parent.parent / "data" / "scratch" / "corpora"

# Languages recognised by gt outline in Phase 1a.
GO_REPOS = {
    "golang/go",
    "kubernetes/kubernetes",
    "jsgerman-oss/blackrim.dev",
}

# Local path for the Blackrim self-reference — no clone needed.
BLACKRIM_LOCAL = Path("/Users/jayse/Code/blackrim")


def dest_dir(org: str, repo: str, ref: str) -> Path:
    return SCRATCH_DIR / f"{org}__{repo}__{ref}"


def parse_corpus(path: Path) -> list[tuple[str, str, str]]:
    """Return list of (org, repo, ref) tuples, skipping comments/blanks."""
    entries = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Expected format: org/repo@ref
        if "@" not in line or "/" not in line:
            print(f"[WARN] malformed entry, skipping: {line!r}", file=sys.stderr)
            continue
        slug, ref = line.rsplit("@", 1)
        org, repo = slug.split("/", 1)
        entries.append((org, repo, ref))
    return entries


def clone_repo(org: str, repo: str, ref: str) -> bool:
    """Clone repo at ref into SCRATCH_DIR. Return True on success."""
    dest = dest_dir(org, repo, ref)
    if dest.exists():
        print(f"[skip-exists] {org}/{repo}@{ref} → {dest}")
        return True

    url = f"https://github.com/{org}/{repo}.git"
    cmd = [
        "git", "clone",
        "--depth=1",
        "--filter=blob:none",
        "--branch", ref,
        url,
        str(dest),
    ]
    print(f"[clone] {org}/{repo}@{ref} …", flush=True)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[ok]    {dest}")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[error] clone failed for {org}/{repo}@{ref}: {exc.stderr.strip()}", file=sys.stderr)
        return False


def main() -> int:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    entries = parse_corpus(CORPUS_FILE)

    for org, repo, ref in entries:
        full_slug = f"{org}/{repo}"

        # --- Non-Go: log and skip -----------------------------------------
        if full_slug not in GO_REPOS:
            print(f"[skip-phase1a] {full_slug}@{ref} — non-Go entry; deferred to Phase 1b")
            continue

        # --- Blackrim self-reference: use local checkout ------------------
        if full_slug == "jsgerman-oss/blackrim.dev":
            dest = dest_dir(org, repo, ref)
            if dest.exists():
                print(f"[skip-exists] {full_slug}@{ref} → {dest} (symlink already present)")
            elif BLACKRIM_LOCAL.exists():
                dest.symlink_to(BLACKRIM_LOCAL)
                print(f"[symlink] {dest} → {BLACKRIM_LOCAL}")
            else:
                print(
                    f"[error] Blackrim local checkout not found at {BLACKRIM_LOCAL}",
                    file=sys.stderr,
                )
            continue

        # --- Regular Go repos: git clone ----------------------------------
        clone_repo(org, repo, ref)

    return 0


if __name__ == "__main__":
    sys.exit(main())
