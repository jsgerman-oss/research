#!/usr/bin/env python3
"""Pull session telemetry for the trim-paper evaluation section.

Reads from the Blackrim repo's git log and emits one JSON record per
commit that touched CLAUDE.md, with the CLAUDE.md size at each SHA.
Stdout is JSON-lines, oldest-first (so the first record is the
baseline for aggregate-trim-results.py).

Usage:
    python scripts/pull-telemetry.py --since 2026-05-08 \\
        --repo /Users/jayse/Code/blackrim \\
        > data/raw/session-telemetry.json

Note: the default --since is 2026-05-09T03:17:00-07:00 so that the
pre-Wave-1 baseline commit (64149950, timestamped 03:18:45 PDT) is
the first record. A bare date like 2026-05-09 resolves to midnight UTC
and would exclude early-morning PDT commits; a post-midnight PDT commit
that preceded the supervisor commit would otherwise become the baseline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    ).strip()


def commits_since(repo: Path, since: str) -> list[str]:
    """Return SHAs of commits since `since` that touched CLAUDE.md, oldest first."""
    out = git(repo, "log", f"--since={since}", "--format=%H", "main", "--", "CLAUDE.md")
    return out.splitlines() if out else []


def commit_meta(repo: Path, sha: str) -> dict:
    fmt = "%H%x1f%aI%x1f%s%x1f%an"
    raw = git(repo, "log", "-1", f"--format={fmt}", sha)
    h, ai, subj, an = raw.split("\x1f")
    return {"sha": h, "author_iso": ai, "subject": subj, "author": an}


def claude_md_size(repo: Path, sha: str) -> dict:
    """Return lines + chars for CLAUDE.md at the given SHA, or zeros if missing."""
    try:
        content = subprocess.check_output(
            ["git", "-C", str(repo), "show", f"{sha}:CLAUDE.md"], text=True
        )
    except subprocess.CalledProcessError:
        return {"lines": 0, "chars": 0}
    return {"lines": content.count("\n"), "chars": len(content)}


def files_in_commit(repo: Path, sha: str) -> list[str]:
    out = git(repo, "show", "--name-only", "--format=", sha)
    return [f for f in out.splitlines() if f]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-05-09T03:17:00-07:00")
    ap.add_argument(
        "--repo", default="/Users/jayse/Code/blackrim", type=Path
    )
    args = ap.parse_args()

    if not args.repo.exists():
        print(f"repo not found: {args.repo}", file=sys.stderr)
        sys.exit(2)

    shas = list(reversed(commits_since(args.repo, args.since)))  # oldest first

    for sha in shas:
        meta = commit_meta(args.repo, sha)
        meta["claude_md"] = claude_md_size(args.repo, sha)
        meta["files_changed"] = files_in_commit(args.repo, sha)
        print(json.dumps(meta))


if __name__ == "__main__":
    main()
