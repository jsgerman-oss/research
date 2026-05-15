#!/usr/bin/env python3
"""
pull-compression-ratios.py — emit JSONL of per-language compression ratios.

Reads from a Blackrim checkout's in-tree bench fixtures and the
`gt compress structure` (alias for `gt outline --bulk` in 1b) command.
Emits one JSONL record per file with fields:

    {"lang": "go", "file": "sample.go", "loc": ...,
     "raw_bytes": ..., "outline_bytes": ..., "ratio": ...,
     "tokens_raw_est": ..., "tokens_outline_est": ..., "tokens_savings": ...}

Token estimates use the per-language ~10-tokens-per-line approximation
documented in §3.1 of the paper (see Assumption 2). For real token
counts under a specific tokenizer, swap the `est_tokens` function for
an `anthropic.tokenizer.count_tokens` call.

§6.2 (Empirical Evaluation — Compression ratios by language) consumes
this script's output via `aggregate-by-language.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

LANG_FIXTURES = {
    "go":         "sample.go",
    "python":     "sample.py",
    "javascript": "sample.js",
    "typescript": "sample.tsx",
}

TOKENS_PER_LINE = 10  # see §3.1 Assumption 2.


def est_tokens(text: str) -> int:
    """Approximate per-line token count; replace for a real tokenizer."""
    return max(1, len(text.splitlines()) * TOKENS_PER_LINE)


def measure_one(gt_bin: Path, fixture_path: Path, lang: str) -> dict:
    raw = fixture_path.read_text()
    loc = len(raw.splitlines())
    raw_bytes = len(raw.encode("utf-8"))

    # `gt outline --format json` (preferred when 1b ships).
    # Falls back to `gt compress structure` for the 1a → 1b transition.
    cmd_outline = [str(gt_bin), "outline", "--format", "markdown", str(fixture_path)]
    cmd_compress = [str(gt_bin), "compress", "structure", "--lang", lang, str(fixture_path)]
    try:
        outline_text = subprocess.check_output(cmd_outline, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        outline_text = subprocess.check_output(cmd_compress, text=True)

    outline_bytes = len(outline_text.encode("utf-8"))
    ratio = outline_bytes / raw_bytes if raw_bytes else 1.0
    tok_raw = est_tokens(raw)
    tok_out = est_tokens(outline_text)
    savings = 1.0 - (tok_out / tok_raw) if tok_raw else 0.0

    return {
        "lang": lang,
        "file": fixture_path.name,
        "loc": loc,
        "raw_bytes": raw_bytes,
        "outline_bytes": outline_bytes,
        "ratio": ratio,
        "tokens_raw_est": tok_raw,
        "tokens_outline_est": tok_out,
        "tokens_savings": savings,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--blackrim-root",
        default=os.environ.get("BLACKRIM_ROOT", str(Path.home() / "Code" / "blackrim")),
        help="Path to a Blackrim checkout (default: $BLACKRIM_ROOT or ~/Code/blackrim).",
    )
    p.add_argument(
        "--fixtures-dir",
        default="cmd/gt/testdata/bench",
        help="Relative path to the bench fixtures inside the Blackrim checkout.",
    )
    args = p.parse_args()

    root = Path(args.blackrim_root)
    gt_bin = root / "bin" / "gt"
    if not gt_bin.exists():
        # Fallback: `go run ./cmd/gt` if a built binary isn't there.
        gt_bin = root / "cmd" / "gt"  # the script will detect later.

    fixtures_dir = root / args.fixtures_dir
    if not fixtures_dir.is_dir():
        print(f"fixtures dir not found: {fixtures_dir}", file=sys.stderr)
        return 2

    for lang, basename in LANG_FIXTURES.items():
        path = fixtures_dir / basename
        if not path.exists():
            print(f"missing fixture {path}", file=sys.stderr)
            continue
        rec = measure_one(gt_bin, path, lang)
        sys.stdout.write(json.dumps(rec) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
