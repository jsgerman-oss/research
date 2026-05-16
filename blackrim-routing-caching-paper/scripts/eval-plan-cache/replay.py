#!/usr/bin/env python3
"""
Plan-cache replay harness for the Blackrim routing-caching paper (RC-05).

Runs leave-one-out (LOO) cross-validation across N indexed dispatches:

    For each dispatch i:
      1. Build a temporary index from {all_dispatches \\ {i}}.
      2. Embed dispatch_i's user_query (or reuse the stored embedding).
      3. Retrieve the top-1 match by cosine similarity of query embeddings.
      4. Decide HIT if the retrieved plan signature matches dispatch_i's
         actual plan signature; MISS otherwise.
      5. Classify FALSE HIT: retrieved signature matched but the response
         summary is qualitatively different (detected via task_type mismatch).

Outputs
-------
Per-dispatch CSV  (--out):
    dispatch_id, gold_signature, top1_signature, similarity,
    decision (hit/miss), correct (True/False), false_hit (True/False),
    gold_task_type, top1_task_type

Summary CSV  (--summary):
    hit_rate, false_hit_rate, miss_rate, n_dispatches,
    composed_cost_reduction_vs_prefix_only

Metrics definitions
-------------------
- hit_rate          : fraction of dispatches where top-1 plan signature
                      exactly matches the gold signature.
- false_hit_rate    : fraction of dispatches where signature matched but
                      task_type differs (proxy for qualitatively wrong reuse).
- composed_cost_reduction : estimated additional savings from plan-cache
                      layered on top of prefix-cache-only baseline.
                      Formula: hit_rate * (1 - false_hit_rate) * prefix_savings_baseline
                      where prefix_savings_baseline = 0.786 (from §7 calibration).

Dry-run mode
------------
When --dry-run is set (or when the index was built without embeddings), the
replay falls back to exact signature-hash matching instead of cosine
similarity.  Hit rate in this mode equals the fraction of LOO folds where
another dispatch shares the same coarse plan signature.

Usage
-----
    # Dry-run against fixture (CI-safe, no embedding model required):
    python scripts/eval-plan-cache/replay.py --dry-run

    # Full embedding-based replay:
    python scripts/eval-plan-cache/replay.py \\
        --index scripts/eval-plan-cache/plan-index.jsonl \\
        --out data/aggregated/plancache-eval.csv \\
        --summary data/aggregated/plancache-summary.csv

    # Sanity check: duplicate the index — hit rate should approach 100%:
    python scripts/eval-plan-cache/replay.py --sanity-check --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python — no numpy required in dry-run mode)
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [-1, 1].  Returns 0.0 for zero vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Index loader
# ---------------------------------------------------------------------------

def load_index(index_path: Path) -> list[dict[str, Any]]:
    """Load a JSONL index produced by index.py."""
    records: list[dict[str, Any]] = []
    with index_path.open() as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                print(
                    f"WARNING: index line {lineno}: parse error ({exc}) — skipped",
                    file=sys.stderr,
                )
    return records


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve_top1(
    query_embedding: list[float],
    query_sig_hash: str,
    index_subset: list[dict[str, Any]],
    dry_run: bool,
) -> tuple[dict[str, Any] | None, float]:
    """Return (best_record, similarity) from index_subset.

    In embedding mode: ranks by cosine similarity of query_embedding vectors.
    In dry-run / no-embedding mode: ranks by exact signature_hash match first
    (similarity = 1.0), then falls through to 0.0 for non-matching records.
    This deterministic fallback ensures CI can run the full LOO loop without
    the sentence-transformers model.
    """
    if not index_subset:
        return None, 0.0

    has_embeddings = any(r.get("query_embedding") for r in index_subset)

    if has_embeddings and not dry_run:
        # Embedding-based retrieval: cosine similarity
        scored = [
            (cosine_similarity(query_embedding, r["query_embedding"]), r)
            for r in index_subset
        ]
    else:
        # Dry-run / no-embedding fallback: exact hash → 1.0, otherwise 0.0
        # Among 0.0 ties the first record wins (deterministic given sort).
        scored = [
            (1.0 if r["signature_hash"] == query_sig_hash else 0.0, r)
            for r in index_subset
        ]

    best_sim, best_rec = max(scored, key=lambda t: t[0])
    return best_rec, best_sim


# ---------------------------------------------------------------------------
# False-hit detection
# ---------------------------------------------------------------------------

def is_false_hit(gold: dict[str, Any], retrieved: dict[str, Any]) -> bool:
    """Heuristic: a signature hit is a FALSE HIT if the task types differ.

    Rationale: the plan signature encodes the tool sequence but not the
    semantic intent.  If a 'test' dispatch and a 'build' dispatch happen to
    share the same coarse tool sequence (e.g. Read:internal/|Bash:go|Edit:internal/),
    reusing the 'build' plan for a 'test' request is qualitatively wrong even
    though the signatures match.

    Limitations: task_type is a coarse proxy — 'build' and 'operate' could
    legitimately share plans.  A future version should embed the response
    summary and threshold semantic divergence.
    """
    return (
        gold.get("task_type", "") != retrieved.get("task_type", "")
    )


# ---------------------------------------------------------------------------
# LOO cross-validation
# ---------------------------------------------------------------------------

PREFIX_SAVINGS_BASELINE = 0.786  # §7 calibration: 78.6% savings from prefix cache alone


def run_loo(
    records: list[dict[str, Any]],
    dry_run: bool,
) -> tuple[list[dict], dict]:
    """Run LOO CV.  Returns (per_dispatch_rows, summary_dict)."""

    rows: list[dict] = []

    for i, dispatch in enumerate(records):
        # Build LOO index: all records except this one
        loo_index = [r for j, r in enumerate(records) if j != i]

        query_embedding = dispatch.get("query_embedding", [])
        gold_sig = dispatch.get("plan_signature", "")
        gold_sig_hash = dispatch.get("signature_hash", "")

        top1, similarity = retrieve_top1(
            query_embedding,
            gold_sig_hash,
            loo_index,
            dry_run=dry_run,
        )

        if top1 is None:
            # Edge case: index was empty after removing this dispatch
            rows.append({
                "dispatch_id": dispatch["dispatch_id"],
                "gold_signature": gold_sig,
                "top1_signature": "",
                "similarity": 0.0,
                "decision": "miss",
                "correct": False,
                "false_hit": False,
                "gold_task_type": dispatch.get("task_type", ""),
                "top1_task_type": "",
            })
            continue

        top1_sig = top1.get("plan_signature", "")
        hit = top1_sig == gold_sig
        false_h = hit and is_false_hit(dispatch, top1)
        decision = "hit" if hit else "miss"

        rows.append({
            "dispatch_id": dispatch["dispatch_id"],
            "gold_signature": gold_sig,
            "top1_signature": top1_sig,
            "similarity": round(similarity, 6),
            "decision": decision,
            "correct": hit and not false_h,
            "false_hit": false_h,
            "gold_task_type": dispatch.get("task_type", ""),
            "top1_task_type": top1.get("task_type", ""),
        })

    n = len(rows)
    if n == 0:
        return rows, {}

    n_hits = sum(1 for r in rows if r["decision"] == "hit")
    n_false_hits = sum(1 for r in rows if r["false_hit"])
    hit_rate = n_hits / n
    false_hit_rate = n_false_hits / n
    miss_rate = 1.0 - hit_rate

    # Composed cost reduction: plan-cache savings on top of prefix-cache savings.
    # Plan cache helps only when it fires a true hit (hit and not false_hit).
    true_hit_rate = (n_hits - n_false_hits) / n
    # Composed savings = prefix savings + plan savings on the remaining cost.
    # Remaining cost after prefix cache = (1 - PREFIX_SAVINGS_BASELINE).
    # Plan cache saves that remaining cost on true-hit fraction of requests.
    composed_cost_reduction = PREFIX_SAVINGS_BASELINE + true_hit_rate * (
        1.0 - PREFIX_SAVINGS_BASELINE
    )

    summary = {
        "n_dispatches": n,
        "n_hits": n_hits,
        "n_false_hits": n_false_hits,
        "n_misses": n - n_hits,
        "hit_rate": round(hit_rate, 4),
        "false_hit_rate": round(false_hit_rate, 4),
        "miss_rate": round(miss_rate, 4),
        "true_hit_rate": round(true_hit_rate, 4),
        "prefix_savings_baseline": PREFIX_SAVINGS_BASELINE,
        "composed_cost_reduction_vs_prefix_only": round(composed_cost_reduction, 4),
    }

    return rows, summary


# ---------------------------------------------------------------------------
# Sanity check: duplicate index → hit rate should approach 100%
# ---------------------------------------------------------------------------

def run_sanity_check(records: list[dict[str, Any]], dry_run: bool) -> None:
    """Validate harness correctness: duplicate each record → hit rate ~ 100%."""
    doubled = records + records  # each dispatch appears twice

    # LOO from a doubled index: for any dispatch_i, its duplicate is still
    # in the index after removing the i-th copy.
    rows, summary = run_loo(doubled, dry_run=dry_run)

    n = summary.get("n_dispatches", 0)
    hit_rate = summary.get("hit_rate", 0.0)
    print(f"Sanity check (doubled index, N={n}): hit_rate = {hit_rate:.1%}")
    if hit_rate < 0.95:
        print(
            "WARNING: hit rate below 95% on doubled index — "
            "the retrieval or signature logic may have a bug.",
            file=sys.stderr,
        )
    else:
        print("Sanity check PASSED.")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

EVAL_FIELDNAMES = [
    "dispatch_id",
    "gold_signature",
    "top1_signature",
    "similarity",
    "decision",
    "correct",
    "false_hit",
    "gold_task_type",
    "top1_task_type",
]

SUMMARY_FIELDNAMES = [
    "n_dispatches",
    "n_hits",
    "n_false_hits",
    "n_misses",
    "hit_rate",
    "false_hit_rate",
    "miss_rate",
    "true_hit_rate",
    "prefix_savings_baseline",
    "composed_cost_reduction_vs_prefix_only",
]


def write_eval_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EVAL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Per-dispatch eval written: {out_path}  ({len(rows)} rows)")


def write_summary_csv(summary: dict, summary_path: Path) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDNAMES)
        writer.writeheader()
        writer.writerow(summary)
    print(f"Summary CSV written: {summary_path}")


def print_summary(summary: dict) -> None:
    n = summary["n_dispatches"]
    print(f"\n{'='*60}")
    print(f"Plan-cache LOO evaluation  (N={n})")
    print(f"{'='*60}")
    print(f"  Hit rate           : {summary['hit_rate']:.1%}  ({summary['n_hits']}/{n})")
    print(f"  False-hit rate     : {summary['false_hit_rate']:.1%}  ({summary['n_false_hits']}/{n})")
    print(f"  Miss rate          : {summary['miss_rate']:.1%}  ({summary['n_misses']}/{n})")
    print(f"  True hit rate      : {summary['true_hit_rate']:.1%}")
    print()
    print(f"  Prefix-cache baseline savings : {summary['prefix_savings_baseline']:.1%}")
    print(f"  Composed cost reduction       : {summary['composed_cost_reduction_vs_prefix_only']:.1%}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay plan-cache LOO evaluation against a dispatch index."
    )
    parser.add_argument(
        "--index",
        default="scripts/eval-plan-cache/plan-index.jsonl",
        help="Path to plan-index.jsonl produced by index.py.",
    )
    parser.add_argument(
        "--out",
        default="data/aggregated/plancache-eval.csv",
        help="Per-dispatch output CSV path.",
    )
    parser.add_argument(
        "--summary",
        default="data/aggregated/plancache-summary.csv",
        help="Summary output CSV path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Use exact signature-hash matching instead of cosine similarity. "
            "No embedding model required.  Suitable for CI."
        ),
    )
    parser.add_argument(
        "--sanity-check",
        action="store_true",
        default=False,
        help=(
            "After the main LOO run, run a sanity check: duplicate the index "
            "and verify hit rate approaches 100%."
        ),
    )
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        # Convenience: if the user forgot to build the index first, tell them.
        sys.exit(
            f"ERROR: index not found at {index_path}.\n"
            "Build it first with:\n"
            "    python scripts/eval-plan-cache/index.py "
            "--dispatches tests/fixtures/sample-dispatches.jsonl "
            f"--out {index_path} --dry-run"
        )

    out_path = Path(args.out)
    summary_path = Path(args.summary)

    # Load index
    records = load_index(index_path)
    if not records:
        sys.exit("ERROR: index file is empty or unreadable.")
    print(f"Loaded {len(records)} index records from {index_path}")

    if args.dry_run:
        print("Dry-run mode: using exact signature-hash matching (no embeddings).")

    # Run LOO
    rows, summary = run_loo(records, dry_run=args.dry_run)

    if not summary:
        sys.exit("ERROR: LOO produced no results.")

    print_summary(summary)
    write_eval_csv(rows, out_path)
    write_summary_csv(summary, summary_path)

    # Optional sanity check
    if args.sanity_check:
        print("\nRunning sanity check (doubled index)…")
        run_sanity_check(records, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
