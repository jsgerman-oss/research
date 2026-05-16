#!/usr/bin/env python3
"""
pull-compression-ratios.py — emit JSONL of per-language compression ratios.

Supports two modes:

  1. **Corpus mode** (default): reads from `scripts/corpus-files/{go,py,js,tsx}/`
     inside the research repo. Each subdirectory holds file-NN.<ext> samples
     collected from open-source repos (see scripts/README.md for provenance).
     This mode does NOT require a `gt` binary — it measures raw byte/LoC
     reduction using the gt outline logic approximated by structural heuristics.

  2. **Legacy single-fixture mode** (`--legacy`): reads from a Blackrim checkout's
     in-tree bench fixtures and invokes `gt outline` / `gt compress structure`.
     Retained for reproducibility of the pre-v2 n=1 measurements in §6 footnote.

Emits one JSONL record per file with fields:

    {"lang": "go", "file": "file-01.go", "loc": ...,
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
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Corpus mode: language → subdirectory name + file extension
# ---------------------------------------------------------------------------
CORPUS_LANGS: dict[str, tuple[str, str]] = {
    "go":         ("go",  ".go"),
    "python":     ("py",  ".py"),
    "javascript": ("js",  ".js"),
    "typescript": ("tsx", ".tsx"),
}

# ---------------------------------------------------------------------------
# Legacy mode: single bench fixtures inside the Blackrim checkout
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Structural outline approximation (corpus mode, no gt binary required)
# ---------------------------------------------------------------------------
# These patterns capture declaration-level structure (type/func/class/const/
# interface/arrow-export/method).  They deliberately do NOT capture bodies,
# which is what `gt outline` suppresses.  The approximation is coarser than
# the real AST walk but consistent across the corpus and sufficient for the
# byte/token ratio measurements reported in §6.2.

_GO_DECL = re.compile(
    r'^(?:func |type |const |var |//|package |import )', re.MULTILINE
)
_PY_DECL = re.compile(
    r'^(?:def |class |@|#|import |from |[A-Z_][A-Z0-9_]* ?=)', re.MULTILINE
)
_JS_DECL = re.compile(
    r'^(?:export |function |class |const |let |var |//|/\*)', re.MULTILINE
)
_TS_DECL = _JS_DECL  # TS shares the same top-level shape for this purpose


_LANG_PATTERN: dict[str, re.Pattern[str]] = {
    "go":         _GO_DECL,
    "python":     _PY_DECL,
    "javascript": _JS_DECL,
    "typescript": _TS_DECL,
}


def _structural_outline(text: str, lang: str) -> str:
    """
    Return a simplified structural outline of *text*.

    Keeps declaration-header lines (matching _LANG_PATTERN[lang]) plus
    blank lines; drops body lines.  This approximates what `gt outline`
    produces without requiring a gt binary.
    """
    pattern = _LANG_PATTERN.get(lang, _GO_DECL)
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped == "\n":
            out.append(line)
        elif pattern.match(line):
            out.append(line)
        # else: body line — drop it
    return "".join(out)


# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------

def measure_corpus_file(filepath: Path, lang: str) -> dict:
    """Measure one file using the structural outline approximation."""
    raw = filepath.read_text(encoding="utf-8", errors="replace")
    loc = len(raw.splitlines())
    raw_bytes = len(raw.encode("utf-8"))

    outline_text = _structural_outline(raw, lang)
    outline_bytes = len(outline_text.encode("utf-8"))
    ratio = outline_bytes / raw_bytes if raw_bytes else 1.0
    tok_raw = est_tokens(raw)
    tok_out = est_tokens(outline_text)
    savings = 1.0 - (tok_out / tok_raw) if tok_raw else 0.0

    return {
        "lang": lang,
        "file": filepath.name,
        "loc": loc,
        "raw_bytes": raw_bytes,
        "outline_bytes": outline_bytes,
        "ratio": round(ratio, 4),
        "tokens_raw_est": tok_raw,
        "tokens_outline_est": tok_out,
        "tokens_savings": round(savings, 4),
    }


def measure_legacy_fixture(gt_bin: Path, fixture_path: Path, lang: str) -> dict:
    """Measure one file by invoking gt outline (legacy mode)."""
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
        "ratio": round(ratio, 4),
        "tokens_raw_est": tok_raw,
        "tokens_outline_est": tok_out,
        "tokens_savings": round(savings, 4),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--corpus-dir",
        default=None,
        help=(
            "Path to the corpus-files directory (default: scripts/corpus-files/ "
            "relative to this script). Each subdirectory go/py/js/tsx holds "
            "file-NN.<ext> samples."
        ),
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help=(
            "Use legacy single-fixture mode: invoke gt from a Blackrim checkout "
            "instead of walking the corpus directory. Reproduces pre-v2 n=1 "
            "measurements (see §6 footnote)."
        ),
    )
    p.add_argument(
        "--blackrim-root",
        default=os.environ.get("BLACKRIM_ROOT", str(Path.home() / "Code" / "blackrim")),
        help="(Legacy mode only) Path to a Blackrim checkout.",
    )
    p.add_argument(
        "--fixtures-dir",
        default="cmd/gt/testdata/bench",
        help="(Legacy mode only) Relative path to bench fixtures inside the checkout.",
    )
    args = p.parse_args()

    if args.legacy:
        return _run_legacy(args)
    return _run_corpus(args)


def _run_corpus(args: argparse.Namespace) -> int:
    script_dir = Path(__file__).parent
    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else script_dir / "corpus-files"

    if not corpus_dir.is_dir():
        print(f"corpus-files dir not found: {corpus_dir}", file=sys.stderr)
        print(
            "Run with --legacy to use the single-fixture mode, or populate "
            "corpus-files/{go,py,js,tsx}/ first.",
            file=sys.stderr,
        )
        return 2

    found_any = False
    for lang, (subdir, ext) in CORPUS_LANGS.items():
        lang_dir = corpus_dir / subdir
        if not lang_dir.is_dir():
            print(f"missing corpus subdir: {lang_dir}", file=sys.stderr)
            continue
        files = sorted(lang_dir.glob(f"*{ext}"))
        if not files:
            print(f"no {ext} files in {lang_dir}", file=sys.stderr)
            continue
        for path in files:
            rec = measure_corpus_file(path, lang)
            sys.stdout.write(json.dumps(rec) + "\n")
            found_any = True

    if not found_any:
        print("no files measured — check corpus-files/ directory", file=sys.stderr)
        return 2
    return 0


def _run_legacy(args: argparse.Namespace) -> int:
    root = Path(args.blackrim_root)
    gt_bin = root / "bin" / "gt"
    if not gt_bin.exists():
        gt_bin = root / "cmd" / "gt"

    fixtures_dir = root / args.fixtures_dir
    if not fixtures_dir.is_dir():
        print(f"fixtures dir not found: {fixtures_dir}", file=sys.stderr)
        return 2

    for lang, basename in LANG_FIXTURES.items():
        path = fixtures_dir / basename
        if not path.exists():
            print(f"missing fixture {path}", file=sys.stderr)
            continue
        rec = measure_legacy_fixture(gt_bin, path, lang)
        sys.stdout.write(json.dumps(rec) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
