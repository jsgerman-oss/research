#!/usr/bin/env python3
"""
run.py — CLI for the TRIM-03 fidelity evaluation harness.

Usage (dry-run, no API key needed):
    python scripts/eval-fidelity/run.py \\
        --prefix-sha eb8c3d0 \\
        --prompts scripts/eval-fidelity/prompts.yml \\
        --dry-run \\
        --out data/aggregated/fidelity-baseline-dryrun.csv

Live run (requires ANTHROPIC_API_KEY):
    python scripts/eval-fidelity/run.py \\
        --prefix-sha eb8c3d0 \\
        --prompts scripts/eval-fidelity/prompts.yml \\
        --api-key-env ANTHROPIC_API_KEY \\
        --model claude-opus-4-7 \\
        --cost-budget-usd 2.0 \\
        --out data/aggregated/fidelity-eb8c3d0.csv

Alternative: pass a local CLAUDE.md file instead of a SHA:
    python scripts/eval-fidelity/run.py \\
        --prefix path/to/CLAUDE.md \\
        --dry-run \\
        --out data/aggregated/fidelity-dryrun-sample.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

import yaml

# rubric.py lives in the same directory as this script
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))

from rubric import RubricResult, score_all  # noqa: E402 (after path setup)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate token cost for Opus 4.7 input (cache-read rate), per 1M tokens.
# Used for pre-flight budget estimation only; not authoritative pricing.
_OPUS_INPUT_CACHE_READ_PER_MTK = 7.50   # USD / million tokens (cache read)
_OPUS_INPUT_CACHE_MISS_PER_MTK = 75.00  # USD / million tokens (cache miss)
_TOKENS_PER_CHAR_APPROX = 0.25          # rough heuristic: ~4 chars / token

_DRY_RUN_RESPONSE = "DRY_RUN"

# Repo root for resolving relative output paths
_REPO_ROOT = Path(__file__).parents[3]  # scripts/eval-fidelity/../../.. = paper root
_PAPER_ROOT = Path(__file__).parents[2]  # scripts/eval-fidelity/../.. = paper root


# ---------------------------------------------------------------------------
# CLAUDE.md loading
# ---------------------------------------------------------------------------

def load_prefix_from_sha(sha: str, blackrim_repo: str) -> str:
    """Extract CLAUDE.md content from a Blackrim git commit."""
    try:
        result = subprocess.run(
            ["git", "-C", blackrim_repo, "show", f"{sha}:CLAUDE.md"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"ERROR: could not read CLAUDE.md at {sha} from {blackrim_repo}", file=sys.stderr)
        print(f"       {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def load_prefix_from_file(path: str) -> str:
    """Load a local CLAUDE.md (or any prefix file) from disk."""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: prefix file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return p.read_text()


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def estimate_cost_usd(
    prefix_text: str,
    prompt_count: int,
    cache_hit_ratio: float = 0.85,
) -> float:
    """
    Estimate total USD cost for a live run.

    Assumes:
      - prefix (CLAUDE.md) is sent as a cached system block; only the first
        call pays cache-miss price, the rest pay cache-read price.
      - Each user prompt is ~50 tokens on average.
      - Each response is ~400 tokens on average.
    """
    prefix_tokens = len(prefix_text) * _TOKENS_PER_CHAR_APPROX
    prompt_tokens_each = 50
    response_tokens_each = 400

    # System block: one cache miss + (N-1) cache reads
    system_cost = (prefix_tokens / 1_000_000) * _OPUS_INPUT_CACHE_MISS_PER_MTK
    if prompt_count > 1:
        system_cost += (prefix_tokens / 1_000_000) * _OPUS_INPUT_CACHE_READ_PER_MTK * (prompt_count - 1)

    # Per-prompt input cost (not cached)
    input_cost = (prompt_tokens_each / 1_000_000) * _OPUS_INPUT_CACHE_MISS_PER_MTK * prompt_count

    # Output cost (not estimated here — use a small multiplier)
    output_cost_per_mtk = 15.0  # rough estimate for Opus output
    output_cost = (response_tokens_each / 1_000_000) * output_cost_per_mtk * prompt_count

    return system_cost + input_cost + output_cost


# ---------------------------------------------------------------------------
# Dry-run response generation
# ---------------------------------------------------------------------------

def generate_dry_run_responses(prompt_ids: list[str]) -> dict[str, str]:
    """Return the literal string DRY_RUN for every prompt."""
    return {pid: _DRY_RUN_RESPONSE for pid in prompt_ids}


def load_responses_from_jsonl(path: str, prompt_ids: list[str]) -> dict[str, str]:
    """
    Read pre-collected responses from a JSONL file. Each line is a JSON object
    with at least `id` and `response` keys. Missing prompts are filled with the
    empty string and reported via stderr.

    Source-agnostic: lets responses come from any provider — direct Anthropic
    API, Claude Code sub-agent dispatch (no API key needed), or a manual run.
    """
    import json
    p = Path(path)
    if not p.exists():
        print(f"ERROR: responses JSONL not found: {path}", file=sys.stderr)
        sys.exit(1)
    out: dict[str, str] = {}
    with open(p) as fh:
        for ln, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw or raw.startswith("//"):
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"ERROR: invalid JSON at line {ln}: {e}", file=sys.stderr)
                sys.exit(1)
            pid = rec.get("id") or rec.get("prompt_id")
            text = rec.get("response") or rec.get("response_text") or ""
            if pid:
                out[pid] = text
    missing = [pid for pid in prompt_ids if pid not in out]
    if missing:
        print(
            f"WARNING: {len(missing)} prompts missing from responses JSONL: "
            f"{missing}. Scored as empty.",
            file=sys.stderr,
        )
        for pid in missing:
            out[pid] = ""
    return out


# ---------------------------------------------------------------------------
# Live API calls
# ---------------------------------------------------------------------------

def generate_live_responses(
    prompts: list[dict],
    prefix_text: str,
    model: str,
    api_key: str,
) -> dict[str, str]:
    """
    Call the Anthropic API once per prompt with the CLAUDE.md as a cached
    system block. Returns mapping from prompt_id → response text.
    """
    try:
        import anthropic  # noqa: PLC0415 (late import intentional)
    except ImportError:
        print(
            "ERROR: 'anthropic' package is required for live runs.\n"
            "       Install with: pip install anthropic",
            file=sys.stderr,
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # System block with prompt caching enabled
    system_block = [
        {
            "type": "text",
            "text": prefix_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    responses: dict[str, str] = {}
    for entry in prompts:
        pid = entry["id"]
        user_prompt = entry["prompt"].strip()
        print(f"  calling API for prompt {pid} …", file=sys.stderr)
        message = client.messages.create(
            model=model,
            max_tokens=600,
            system=system_block,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = message.content[0].text if message.content else ""
        responses[pid] = text

    return responses


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

_CSV_FIELDS = [
    "prompt_id",
    "dimension",
    "prefix_sha",
    "response_chars",
    "hit_expected",
    "total_expected",
    "hit_forbidden",
    "total_forbidden",
    "score",
    "status",
    "notes",
]


def write_csv(
    results: list[RubricResult],
    responses: dict[str, str],
    out_path: Path,
    prefix_sha: str,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for r in results:
            response_text = responses.get(r.prompt_id, "")
            writer.writerow(
                {
                    "prompt_id": r.prompt_id,
                    "dimension": r.dimension,
                    "prefix_sha": prefix_sha,
                    "response_chars": len(response_text),
                    "hit_expected": r.hit_expected,
                    "total_expected": r.total_expected,
                    "hit_forbidden": r.hit_forbidden,
                    "total_forbidden": r.total_forbidden,
                    "score": r.score,
                    "status": r.status,
                    "notes": r.notes,
                }
            )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: list[RubricResult], dry_run: bool) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    unscored = sum(1 for r in results if r.status == "unscored")
    avg_score = sum(r.score for r in results) / total if total else 0.0

    print(f"\n{'DRY-RUN ' if dry_run else ''}Fidelity Eval Summary")
    print(f"  total prompts : {total}")
    print(f"  pass          : {passed}")
    print(f"  fail          : {failed}")
    print(f"  unscored      : {unscored}")
    print(f"  avg score     : {avg_score:.3f}")
    pass_rate = passed / total if total else 0.0
    print(f"  pass rate     : {pass_rate:.1%}")
    if dry_run:
        print(
            "\n  NOTE: dry-run uses literal 'DRY_RUN' responses. All prompts\n"
            "  that require specific substrings will fail — this is expected.\n"
            "  The important thing is that the rubric ran and the CSV was produced."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TRIM-03 fidelity eval harness — measure instruction-following fidelity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    prefix_group = parser.add_mutually_exclusive_group(required=True)
    prefix_group.add_argument(
        "--prefix-sha",
        metavar="SHA",
        help="Git commit SHA in the Blackrim repo to read CLAUDE.md from.",
    )
    prefix_group.add_argument(
        "--prefix",
        metavar="PATH",
        help="Path to a local CLAUDE.md / prefix file (alternative to --prefix-sha).",
    )

    parser.add_argument(
        "--prompts",
        default=str(_SCRIPT_DIR / "prompts.yml"),
        help="Path to prompts.yml (default: scripts/eval-fidelity/prompts.yml).",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        help=(
            "Output CSV path. Defaults to "
            "data/aggregated/fidelity-<prefix-sha>.csv "
            "(relative to the paper root)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip API calls; use 'DRY_RUN' as synthetic response for all prompts.",
    )
    parser.add_argument(
        "--responses-jsonl",
        metavar="PATH",
        help=(
            "Path to a JSONL file with pre-collected responses (one "
            "{id, response} per line). Bypasses both --dry-run and the live "
            "API path; lets responses come from any provider (e.g. Claude "
            "Code sub-agent dispatch — no API key required)."
        ),
    )
    parser.add_argument(
        "--api-key-env",
        default="ANTHROPIC_API_KEY",
        metavar="ENV_VAR",
        help="Name of the env var holding the Anthropic API key (default: ANTHROPIC_API_KEY).",
    )
    parser.add_argument(
        "--model",
        default="claude-opus-4-7",
        help="Anthropic model ID for live runs (default: claude-opus-4-7).",
    )
    parser.add_argument(
        "--cost-budget-usd",
        type=float,
        default=2.0,
        metavar="USD",
        help="Hard cost cap in USD; refuses live run if estimated cost exceeds this (default: 2.0).",
    )
    parser.add_argument(
        "--blackrim-repo",
        default="/Users/jayse/Code/blackrim",
        help="Path to the Blackrim repo (used when --prefix-sha is specified).",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # --- Load prompts ---
    prompts_path = Path(args.prompts)
    if not prompts_path.exists():
        print(f"ERROR: prompts file not found: {prompts_path}", file=sys.stderr)
        sys.exit(1)
    with open(prompts_path) as f:
        data = yaml.safe_load(f)
    prompts: list[dict] = data.get("prompts", [])
    if not prompts:
        print("ERROR: no prompts found in prompts.yml", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(prompts)} prompts from {prompts_path}")

    # --- Determine prefix label for file naming ---
    if args.prefix_sha:
        prefix_label = args.prefix_sha
    else:
        # Derive a short label from the file path
        prefix_label = Path(args.prefix).stem.replace(" ", "-")

    # --- Determine output path ---
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = _PAPER_ROOT / "data" / "aggregated" / f"fidelity-{prefix_label}.csv"

    # --- Load prefix (CLAUDE.md content) ---
    if args.prefix_sha:
        print(f"Loading CLAUDE.md from Blackrim SHA {args.prefix_sha} …")
        prefix_text = load_prefix_from_sha(args.prefix_sha, args.blackrim_repo)
    else:
        print(f"Loading prefix from file: {args.prefix}")
        prefix_text = load_prefix_from_file(args.prefix)
    print(f"  prefix length: {len(prefix_text):,} chars")

    # --- Dry-run, pre-collected responses, or live ---
    if args.responses_jsonl:
        print(f"Loading pre-collected responses from {args.responses_jsonl} …")
        prompt_ids = [p["id"] for p in prompts if p.get("id")]
        responses = load_responses_from_jsonl(args.responses_jsonl, prompt_ids)
    elif args.dry_run:
        print("Dry-run mode — skipping API calls.")
        prompt_ids = [p["id"] for p in prompts if p.get("id")]
        responses = generate_dry_run_responses(prompt_ids)
    else:
        # Cost pre-flight check
        estimated_cost = estimate_cost_usd(prefix_text, len(prompts))
        print(f"Estimated cost: ${estimated_cost:.4f} USD (budget: ${args.cost_budget_usd:.2f} USD)")
        if estimated_cost > args.cost_budget_usd:
            print(
                f"ERROR: estimated cost ${estimated_cost:.4f} exceeds budget "
                f"${args.cost_budget_usd:.2f}. Aborting.",
                file=sys.stderr,
            )
            sys.exit(1)

        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            print(
                f"ERROR: environment variable {args.api_key_env} is not set.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Running live eval with model {args.model} …")
        responses = generate_live_responses(prompts, prefix_text, args.model, api_key)

    # --- Score ---
    results = score_all(prompts, responses)

    # --- Write CSV ---
    write_csv(results, responses, out_path, prefix_label)
    print(f"\nCSV written to: {out_path}")
    print(f"  rows: {len(results)}")

    # --- Summary ---
    print_summary(results, dry_run=args.dry_run and not args.responses_jsonl)


if __name__ == "__main__":
    main()
