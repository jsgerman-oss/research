#!/usr/bin/env python3
"""
fill-paired-trace-macros.py — populate TBD macros in §6.7 with real eval data.

Reads the three figures-data JSON files produced by e2e-paired-traces.py
(Stage 3 of the paired-trace pipeline) and rewrites the four placeholder
macros in sections/06-evaluation.tex:

    \headlineDeltaTokens{TBD}
    \headlineDeltaTokensCI{TBD}
    \successProportionAtLeastZero{TBD}
    \successProportionCI{TBD}

The rewrite is idempotent: running it again with the same JSON produces the
same .tex file.  The operation is safe to re-run after a re-eval.

Usage:
    python3 scripts/fill-paired-trace-macros.py

Options:
    --figures-dir   Path to figures-data/ directory
                    (default: data/scratch/paper-v6.7/figures-data/)
    --eval-tex      Path to 06-evaluation.tex
                    (default: sections/06-evaluation.tex)
    --dry-run       Print the replacements without writing

Design reference: docs/design/paired-trace-harness.md §8.
bd issue: blackrim-0cq7 (F6 of wy1l).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_tokens(val: float) -> str:
    """Format a token delta for the headline macro.

    Negative = savings; render as e.g. "-3{,}421" (LaTeX thousands separator).
    """
    iv = int(round(val))
    sign = "-" if iv < 0 else "+"
    abs_str = f"{abs(iv):,}".replace(",", "{,}")
    return f"${sign}{abs_str}$"


def _fmt_tokens_ci(lo: float, hi: float) -> str:
    """Format a BCa CI on token delta as "$[lo, hi]$"."""

    def _tok(v: float) -> str:
        iv = int(round(v))
        sign = "-" if iv < 0 else "+"
        abs_str = f"{abs(iv):,}".replace(",", "{,}")
        return f"{sign}{abs_str}"

    return f"$[{_tok(lo)},\;{_tok(hi)}]$"


def _fmt_prop(val: float) -> str:
    """Format a proportion as a percentage, e.g. "84\\%"."""
    return f"{round(val * 100, 1):.1f}\\%"


def _fmt_prop_ci(lo: float, hi: float) -> str:
    """Format a Wilson CI on a proportion, e.g. "$[72.1\\%, 91.4\\%]$"."""
    return f"$[{round(lo * 100, 1):.1f}\\%,\;{round(hi * 100, 1):.1f}\\%]$"


# ---------------------------------------------------------------------------
# Macro substitution
# ---------------------------------------------------------------------------


def _replace_macro(tex: str, macro_name: str, new_value: str) -> str:
    r"""Replace \macroname{<anything>} with \macroname{new_value}.

    Matches:
        \headlineDeltaTokens{TBD}
        \headlineDeltaTokens{some old value}
        etc.

    The replacement is done only on the \newcommand definition line so it
    is idempotent and does not corrupt \headlineDeltaTokens used in prose.
    """
    pattern = re.compile(
        r'(\\newcommand\{\\' + re.escape(macro_name) + r'\})\{[^}]*\}',
    )
    replacement = r'\g<1>{' + new_value + r'}'
    count = len(pattern.findall(tex))
    if count == 0:
        print(f"  [WARN] macro \\{macro_name} not found in .tex — skipping", file=sys.stderr)
        return tex
    return pattern.sub(replacement, tex)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Populate §6.7 TBD macros from eval figures-data JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=Path("data/scratch/paper-v6.7/figures-data"),
        help="Directory containing paired-*.json files (default: data/scratch/paper-v6.7/figures-data/)",
    )
    parser.add_argument(
        "--eval-tex",
        type=Path,
        default=Path("sections/06-evaluation.tex"),
        help="Path to 06-evaluation.tex (default: sections/06-evaluation.tex)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print macro values without writing the .tex file",
    )
    args = parser.parse_args(argv)

    # Load JSON data files
    tokens_path = args.figures_dir / "paired-tokens-distribution.json"
    success_path = args.figures_dir / "paired-success-distribution.json"

    for fp in (tokens_path, success_path):
        if not fp.exists():
            print(f"[ERROR] {fp} not found — run e2e-paired-traces.py first", file=sys.stderr)
            return 1

    tokens_data = json.loads(tokens_path.read_text(encoding="utf-8"))
    success_data = json.loads(success_path.read_text(encoding="utf-8"))

    # Compute macro values
    headline_delta = _fmt_tokens(tokens_data["median"])
    headline_ci = _fmt_tokens_ci(tokens_data["bca_lo"], tokens_data["bca_hi"])
    prop_nonneg = _fmt_prop(success_data["prop_nonneg"])
    prop_ci = _fmt_prop_ci(success_data["wilson_lo"], success_data["wilson_hi"])

    print("[INFO] computed macro values:", file=sys.stderr)
    print(f"  \\headlineDeltaTokens         = {headline_delta}", file=sys.stderr)
    print(f"  \\headlineDeltaTokensCI       = {headline_ci}", file=sys.stderr)
    print(f"  \\successProportionAtLeastZero = {prop_nonneg}", file=sys.stderr)
    print(f"  \\successProportionCI          = {prop_ci}", file=sys.stderr)

    if args.dry_run:
        print("[INFO] --dry-run: not writing .tex file", file=sys.stderr)
        return 0

    if not args.eval_tex.exists():
        print(f"[ERROR] {args.eval_tex} not found", file=sys.stderr)
        return 1

    tex = args.eval_tex.read_text(encoding="utf-8")

    tex = _replace_macro(tex, "headlineDeltaTokens", headline_delta)
    tex = _replace_macro(tex, "headlineDeltaTokensCI", headline_ci)
    tex = _replace_macro(tex, "successProportionAtLeastZero", prop_nonneg)
    tex = _replace_macro(tex, "successProportionCI", prop_ci)

    args.eval_tex.write_text(tex, encoding="utf-8")
    print(f"[DONE] wrote {args.eval_tex}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
