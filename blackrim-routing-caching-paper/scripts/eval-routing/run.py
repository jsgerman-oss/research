#!/usr/bin/env python3
"""
Routing evaluation harness for the Blackrim routing-caching paper.

Loads 50 hand-labelled turns, runs a named router against them, and
emits per-turn and summary CSVs.  No API calls — all built-in routers
are deterministic.

Usage:
    python run.py --router always-opus \\
        --turns-dir scripts/eval-routing/turns/ \\
        --labels scripts/eval-routing/labels.yml \\
        --out data/aggregated/routing-eval-always-opus.csv

Pricing constants (illustrative, per million input tokens):
    haiku  : $0.25
    sonnet : $3.00
    opus   : $15.00
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path
from typing import Literal

import yaml  # PyYAML — stdlib-free fallback below if missing

# ---------------------------------------------------------------------------
# Pricing (USD per million input tokens — illustrative)
# ---------------------------------------------------------------------------
TIER_COST_PER_MTOK: dict[str, float] = {
    "haiku": 0.25,
    "sonnet": 3.00,
    "opus": 15.00,
}

TIERS: list[str] = ["haiku", "sonnet", "opus"]

# ---------------------------------------------------------------------------
# Router base class
# ---------------------------------------------------------------------------


class Router:
    """Base class for all routers.  Subclass and implement ``route``."""

    name: str = "base"

    def route(self, turn: dict) -> str:
        """Return predicted tier for *turn*.

        Args:
            turn: dict loaded from a turn-NN.json file.  Relevant fields:
                  ``user_prompt`` (str), ``prompt_char_length`` (int),
                  ``tools_used`` (list[str]).

        Returns:
            One of "haiku", "sonnet", "opus".
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Built-in routers
# ---------------------------------------------------------------------------


class AlwaysOpusRouter(Router):
    """Baseline: every turn → opus.

    Expected behaviour: 100% recall on opus-gold turns, 0% precision on
    haiku/sonnet gold turns.  Overall accuracy equals the fraction of opus
    turns in the labelled set.
    """

    name = "always-opus"

    def route(self, turn: dict) -> str:  # noqa: ARG002
        return "opus"


class AlwaysSonnetRouter(Router):
    """Baseline: every turn → sonnet."""

    name = "always-sonnet"

    def route(self, turn: dict) -> str:  # noqa: ARG002
        return "sonnet"


class RandomUniformRouter(Router):
    """Baseline: uniform random choice over the three tiers.

    Seeded for reproducibility; expected accuracy ≈ 33%.
    """

    name = "random-uniform"

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def route(self, turn: dict) -> str:  # noqa: ARG002
        return self._rng.choice(TIERS)


class LengthHeuristicRouter(Router):
    """Baseline: route by prompt character length.

    Thresholds (chars):
        < 300    → haiku
        300–1500 → sonnet
        > 1500   → opus
    """

    name = "length-heuristic"

    def route(self, turn: dict) -> str:
        n = turn.get("prompt_char_length", len(turn.get("user_prompt", "")))
        if n < 300:
            return "haiku"
        if n <= 1500:
            return "sonnet"
        return "opus"


class SemanticSimilarityRouter(Router):
    """Stub for the RC-04 semantic-similarity router.

    Currently returns haiku for every turn so the harness can run
    end-to-end without a live model.  RC-04 will replace this body with
    an embedding-based classifier.
    """

    name = "semantic-similarity"

    def route(self, turn: dict) -> str:  # noqa: ARG002
        # TODO(RC-04): replace with embedding cosine-similarity lookup.
        return "haiku"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ROUTERS: dict[str, type[Router]] = {
    "always-opus": AlwaysOpusRouter,
    "always-sonnet": AlwaysSonnetRouter,
    "random-uniform": RandomUniformRouter,
    "length-heuristic": LengthHeuristicRouter,
    "semantic-similarity": SemanticSimilarityRouter,
}


def get_router(name: str) -> Router:
    if name not in ROUTERS:
        valid = ", ".join(sorted(ROUTERS))
        sys.exit(f"Unknown router '{name}'.  Valid options: {valid}")
    return ROUTERS[name]()


# ---------------------------------------------------------------------------
# Cost helpers
# ---------------------------------------------------------------------------

# Assume a fixed average prompt length of 500 tokens for cost calculations.
# Actual token counts are not available in the dry-run harness; the number is
# illustrative and consistent across routers so relative comparisons hold.
AVG_PROMPT_TOKENS = 500


def cost_usd(tier: str, tokens: int = AVG_PROMPT_TOKENS) -> float:
    """Return cost in USD for *tokens* input tokens at *tier* pricing."""
    return TIER_COST_PER_MTOK[tier] * tokens / 1_000_000


def cost_saved_vs_opus(pred_tier: str, tokens: int = AVG_PROMPT_TOKENS) -> float:
    """Positive number if pred_tier is cheaper than opus; negative if more expensive."""
    return cost_usd("opus", tokens) - cost_usd(pred_tier, tokens)


def cost_of_mistake(gold_tier: str, pred_tier: str, tokens: int = AVG_PROMPT_TOKENS) -> float:
    """Cost incurred by routing to a cheaper tier than gold (quality risk proxy).

    Defined as the price difference between gold and predicted tier when
    predicted is cheaper than gold (under-routing).  Zero if pred >= gold
    in cost (over-routing or correct).
    """
    gold_cost = cost_usd(gold_tier, tokens)
    pred_cost = cost_usd(pred_tier, tokens)
    if pred_cost < gold_cost:
        # Under-routed: potential quality loss
        return gold_cost - pred_cost
    return 0.0


# ---------------------------------------------------------------------------
# Per-tier metrics
# ---------------------------------------------------------------------------


def compute_metrics(
    rows: list[dict],
) -> dict[str, dict[str, float]]:
    """Return per-tier {precision, recall, F1} and overall accuracy.

    Ambiguous turns (gold_tier == "ambiguous") are excluded.
    """
    valid = [r for r in rows if r["gold_tier"] != "ambiguous"]
    total = len(valid)

    metrics: dict[str, dict] = {}
    for tier in TIERS:
        tp = sum(1 for r in valid if r["gold_tier"] == tier and r["pred_tier"] == tier)
        fp = sum(1 for r in valid if r["gold_tier"] != tier and r["pred_tier"] == tier)
        fn = sum(1 for r in valid if r["gold_tier"] == tier and r["pred_tier"] != tier)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        metrics[tier] = {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}

    correct = sum(1 for r in valid if r["correct"])
    metrics["overall"] = {
        "accuracy": correct / total if total > 0 else 0.0,
        "total": total,
        "correct": correct,
    }
    return metrics


# ---------------------------------------------------------------------------
# YAML loader with stdlib fallback
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> dict:
    try:
        import yaml as _yaml  # noqa: PLC0415

        with path.open() as f:
            return _yaml.safe_load(f)
    except ImportError:
        # Minimal YAML subset parser (handles only our labels.yml format)
        raise RuntimeError(
            "PyYAML is required.  Install it with: pip install pyyaml"
        ) from None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score a router against the 50-turn hand-labelled test set."
    )
    parser.add_argument(
        "--router",
        required=True,
        choices=sorted(ROUTERS),
        help="Router to evaluate.",
    )
    parser.add_argument(
        "--turns-dir",
        default="scripts/eval-routing/turns/",
        help="Directory containing turn-NN.json files.",
    )
    parser.add_argument(
        "--labels",
        default="scripts/eval-routing/labels.yml",
        help="Path to labels.yml.",
    )
    parser.add_argument(
        "--out",
        required=False,
        help=(
            "Output CSV path for per-turn results.  Defaults to "
            "data/aggregated/routing-eval-<router>.csv"
        ),
    )
    args = parser.parse_args()

    turns_dir = Path(args.turns_dir)
    labels_path = Path(args.labels)
    out_path = Path(args.out) if args.out else Path(f"data/aggregated/routing-eval-{args.router}.csv")

    # Load labels
    label_data = load_yaml(labels_path)
    gold: dict[str, str] = {
        entry["turn_id"]: entry["should_be_tier"]
        for entry in label_data["labels"]
    }

    # Load turns
    turn_files = sorted(turns_dir.glob("turn-*.json"))
    if not turn_files:
        sys.exit(f"No turn files found in {turns_dir}")

    turns: list[dict] = []
    for tf in turn_files:
        with tf.open() as f:
            turns.append(json.load(f))

    # Build router
    router = get_router(args.router)

    # Run evaluation
    rows: list[dict] = []
    for turn in turns:
        tid = turn["id"]
        gold_tier = gold.get(tid, "ambiguous")
        pred_tier = router.route(turn)

        correct = pred_tier == gold_tier and gold_tier != "ambiguous"
        saved = cost_saved_vs_opus(pred_tier) if gold_tier != "ambiguous" else 0.0
        mistake = cost_of_mistake(gold_tier, pred_tier) if gold_tier != "ambiguous" else 0.0

        rows.append(
            {
                "turn_id": tid,
                "gold_tier": gold_tier,
                "pred_tier": pred_tier,
                "correct": int(correct),
                "cost_saved_vs_opus_usd": round(saved, 8),
                "cost_of_mistake_usd": round(mistake, 8),
            }
        )

    # Write per-turn CSV
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["turn_id", "gold_tier", "pred_tier", "correct", "cost_saved_vs_opus_usd", "cost_of_mistake_usd"]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Per-turn results written to {out_path}  ({len(rows)} rows)")

    # Compute and print metrics
    metrics = compute_metrics(rows)

    print(f"\n{'='*60}")
    print(f"Router: {args.router}")
    print(f"{'='*60}")
    valid_count = metrics["overall"]["total"]
    print(f"Turns evaluated (excl. ambiguous): {valid_count}")
    print(f"Accuracy: {metrics['overall']['accuracy']:.1%}  ({metrics['overall']['correct']}/{valid_count} correct)")
    print()
    for tier in TIERS:
        m = metrics[tier]
        print(
            f"  {tier:8s}  P={m['precision']:.3f}  R={m['recall']:.3f}  F1={m['f1']:.3f}"
            f"  (TP={m['tp']} FP={m['fp']} FN={m['fn']})"
        )

    total_saved = sum(r["cost_saved_vs_opus_usd"] for r in rows)
    total_mistake = sum(r["cost_of_mistake_usd"] for r in rows)
    print(f"\nCost savings vs always-opus : ${total_saved:.6f}")
    print(f"Cost of under-routing       : ${total_mistake:.6f}")

    # Write summary CSV
    summary_path = out_path.parent / f"routing-summary-{args.router}.csv"
    summary_rows = []
    for tier in TIERS:
        m = metrics[tier]
        summary_rows.append(
            {
                "router": args.router,
                "tier": tier,
                "precision": round(m["precision"], 4),
                "recall": round(m["recall"], 4),
                "f1": round(m["f1"], 4),
                "tp": m["tp"],
                "fp": m["fp"],
                "fn": m["fn"],
            }
        )
    summary_rows.append(
        {
            "router": args.router,
            "tier": "overall",
            "precision": "",
            "recall": "",
            "f1": "",
            "tp": metrics["overall"]["correct"],
            "fp": valid_count - metrics["overall"]["correct"],
            "fn": "",
        }
    )

    summary_fieldnames = ["router", "tier", "precision", "recall", "f1", "tp", "fp", "fn"]
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"\nSummary CSV written to {summary_path}")

    # Append to aggregated baseline results CSV
    # Resolve relative to the --out path's grandparent (data/aggregated/)
    # so the harness works regardless of CWD.
    baseline_path = out_path.parent / "routing-baseline-results.csv"
    baseline_exists = baseline_path.exists()
    macro_f1 = sum(metrics[t]["f1"] for t in TIERS) / len(TIERS)
    baseline_row = {
        "router": args.router,
        "accuracy": round(metrics["overall"]["accuracy"], 4),
        "macro_f1": round(macro_f1, 4),
        "haiku_f1": round(metrics["haiku"]["f1"], 4),
        "sonnet_f1": round(metrics["sonnet"]["f1"], 4),
        "opus_f1": round(metrics["opus"]["f1"], 4),
        "total_cost_saved_usd": round(total_saved, 6),
        "total_cost_of_mistakes_usd": round(total_mistake, 6),
    }
    baseline_fieldnames = list(baseline_row.keys())
    with baseline_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=baseline_fieldnames)
        if not baseline_exists:
            writer.writeheader()
        writer.writerow(baseline_row)
    print(f"Baseline row appended to {baseline_path}")


if __name__ == "__main__":
    main()
