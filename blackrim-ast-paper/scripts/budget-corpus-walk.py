#!/usr/bin/env python3
"""
budget-corpus-walk.py — measure outline token-budget conformance across Go repos.

For each .go file (LoC ≥ 200, non-vendor, non-testdata, non-test/gen suffix),
runs `gt outline --format json`, estimates token count, and emits one JSONL
record per file.

Emits to stdout; redirect to data/raw/budget-corpus.jsonl.

Token budget B = 300 (paper §6.3 target).

Token estimation:
  - JSON output available: len(json_string) / 4  (UTF-8 chars per token)
  - Fallback (Markdown): newline_count × 10  (Assumption 2, §3.1)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRATCH_DIR = Path(__file__).parent.parent / "data" / "scratch" / "corpora"
BLACKRIM_LOCAL = Path("/Users/jayse/Code/blackrim")

# Paper §6.3 budget
TOKEN_BUDGET = 300

# Cap per repo to keep wall-clock time bounded
FILES_PER_REPO_CAP = 200

GT_BIN = "gt"  # must be on PATH

# Directories / filename patterns to skip
SKIP_DIRS = {"vendor", "testdata", ".git"}
SKIP_SUFFIXES = {"_test.go", "_gen.go"}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    for skip_dir in SKIP_DIRS:
        if f"/{skip_dir}/" in str(path) or str(path).endswith(f"/{skip_dir}"):
            return True
    name = path.name
    for sfx in SKIP_SUFFIXES:
        if name.endswith(sfx):
            return True
    return False


def count_loc(path: Path) -> int:
    try:
        return len(path.read_text(errors="replace").splitlines())
    except OSError:
        return 0


def run_outline(path: Path) -> tuple[str, bool]:
    """Run gt outline on path.  Return (markdown_output, gt_succeeded).

    We always use the Markdown rendering for token estimation — this is what
    the LLM actually sees when we slot the outline into a prompt.  The JSON
    format includes full AST metadata and is ~5–10× larger; using chars/4
    on JSON would systematically over-count tokens relative to the paper's
    budget B = 300.

    If the Markdown command fails, return ("", False) so the caller can skip.
    """
    try:
        out = subprocess.check_output(
            [GT_BIN, "outline", str(path)],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return out, True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "", False


def estimate_tokens(output: str, is_json: bool) -> int:
    """Estimate tokens from the Markdown outline.

    Primary: chars/4 (UTF-8 byte count / 4) — tighter than the line-based
    approximation for dense identifier-heavy outlines.
    Fallback (is_json=False was the old JSON path; kept for callers that
    still pass False): lines × 10  (Assumption 2, §3.1).
    In practice is_json is always False now.
    """
    # Use chars/4 on the Markdown rendering as the primary estimate.
    return max(1, len(output.encode("utf-8")) // 4)


def walk_repo(repo_name: str, root: Path) -> list[dict]:
    records: list[dict] = []
    candidates: list[Path] = []

    for path in root.rglob("*.go"):
        if should_skip(path):
            continue
        loc = count_loc(path)
        if loc < 200:
            continue
        candidates.append(path)
        if len(candidates) >= FILES_PER_REPO_CAP:
            print(
                f"[cap] {repo_name}: reached {FILES_PER_REPO_CAP}-file cap, stopping walk",
                file=sys.stderr,
            )
            break

    total = len(candidates)
    print(f"[walk] {repo_name}: {total} candidate files", file=sys.stderr)

    for i, path in enumerate(candidates, 1):
        if i % 20 == 0:
            print(f"[progress] {repo_name}: {i}/{total}", file=sys.stderr)

        output, is_json = run_outline(path)
        if not output:
            print(f"[warn] outline failed: {path}", file=sys.stderr)
            continue

        outline_bytes = len(output.encode("utf-8"))
        tokens = estimate_tokens(output, is_json)
        loc = count_loc(path)

        record = {
            "repo": repo_name,
            "file": str(path),
            "loc": loc,
            "outline_bytes": outline_bytes,
            "outline_tokens_est": tokens,
            "within_budget": tokens <= TOKEN_BUDGET,
        }
        records.append(record)

    return records


def main() -> int:
    if not SCRATCH_DIR.exists():
        print(
            f"[error] scratch dir not found: {SCRATCH_DIR}\n"
            "Run clone-corpus.py first.",
            file=sys.stderr,
        )
        return 2

    # Enumerate repos: each subdir of SCRATCH_DIR is one corpus entry.
    repo_dirs: list[tuple[str, Path]] = []
    for entry in sorted(SCRATCH_DIR.iterdir()):
        if not (entry.is_dir() or entry.is_symlink()):
            continue
        # Resolve symlinks for walking; keep original name for labelling.
        resolved = entry.resolve()
        repo_dirs.append((entry.name, resolved))

    if not repo_dirs:
        print("[error] no repos found in scratch dir", file=sys.stderr)
        return 2

    total_records = 0
    for repo_name, root in repo_dirs:
        print(f"[start] {repo_name}", file=sys.stderr)
        records = walk_repo(repo_name, root)
        for rec in records:
            sys.stdout.write(json.dumps(rec) + "\n")
        sys.stdout.flush()
        total_records += len(records)
        print(f"[done]  {repo_name}: {len(records)} records emitted", file=sys.stderr)

    print(f"[total] {total_records} records", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
