#!/usr/bin/env python3
"""
replay.py — replay 4 policies against the advisor-decisions trace.

Policies replayed
-----------------
1. cc-ts          : the recorded conservative Thompson Sampling advisor
                    (recommended_tier is read directly from the JSONL).
2. static-fm      : static-frontmatter mapping (agent → tier, shape ignored).
3. epsilon-greedy : ε-greedy bandit (ε=0.10, seeded from eval-triggered obs).
4. opus-default   : always opus.

Cost model
----------
Input prices (per million tokens, matching Anthropic public sheet used by
aggregate-by-shape.py and the paper's §6):

    haiku   $0.25 / MTok input,  $0.50  / MTok output  (output = 2× input)
    sonnet  $3.00 / MTok input,  $6.00  / MTok output
    opus    $15.00 / MTok input, $30.00 / MTok output

Because the JSONL records do not carry per-dispatch token counts, we use
a **synthetic representative token budget per dispatch** derived from the
mean observed in the production trace (1 200 input tokens, 400 output tokens
per call — rounded figures for exposition; the paper states these explicitly
as illustrative assumptions, not measured averages).

Cost per dispatch = (input_toks / 1e6) × input_price
                  + (output_toks / 1e6) × output_price

Quality model (ILLUSTRATIVE — not measured)
-------------------------------------------
cc-ts quality is assumed to be the baseline: 1.000 (normalised).

For any dispatch where a baseline policy chose a tier *below* the cc-ts
recommendation, we apply a conservative 5 pp degradation per tier step down.
For dispatches where a baseline chose the *same or higher* tier as cc-ts, no
quality penalty is applied.

This is an **illustrative worst-case estimate**, not a measured outcome.
Real quality data requires running the held-out eval fixtures (eval-fixtures.jsonl,
currently a TODO in the pipeline).  The paper is explicit about this.

Output
------
data/aggregated/baseline-comparison.csv — one row per policy:
    policy, total_cost_usd, n_haiku, n_sonnet, n_opus,
    est_quality_score, vs_cc_ts_pct
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve paths relative to the repo root (two levels up from this file).
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
_PAPER_ROOT = _SCRIPTS.parent

_DECISIONS_PATH = _PAPER_ROOT / "data" / "raw" / "advisor-decisions.jsonl"
_EVAL_OBS_PATH = _PAPER_ROOT / "data" / "raw" / "eval-triggered-observations.jsonl"
_OUTPUT_CSV = _PAPER_ROOT / "data" / "aggregated" / "baseline-comparison.csv"

# ---------------------------------------------------------------------------
# Add scripts/ to sys.path so we can import sibling baseline modules cleanly
# without installing anything.
# ---------------------------------------------------------------------------
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import static_frontmatter  # noqa: E402
import epsilon_greedy       # noqa: E402
import opus_default         # noqa: E402

# ---------------------------------------------------------------------------
# Pricing (illustrative representative values — stated explicitly in paper)
# ---------------------------------------------------------------------------
_PRICES = {
    0: {"input": 0.25,  "output": 0.50},   # haiku
    1: {"input": 3.00,  "output": 6.00},   # sonnet
    2: {"input": 15.00, "output": 30.00},  # opus
}

# Synthetic per-dispatch token budget (illustrative — see module docstring)
_INPUT_TOKS  = 1_200   # representative input tokens per dispatch
_OUTPUT_TOKS =   400   # representative output tokens per dispatch

# Quality penalty per tier step below cc-ts recommendation (illustrative)
_QUALITY_PENALTY_PER_STEP = 0.05


def _dispatch_cost(tier: int) -> float:
    """Cost in USD for one dispatch at the given tier."""
    p = _PRICES[tier]
    return (_INPUT_TOKS / 1e6) * p["input"] + (_OUTPUT_TOKS / 1e6) * p["output"]


def _quality_penalty(rec_tier: int, cc_ts_tier: int) -> float:
    """Illustrative quality penalty relative to cc-ts recommendation."""
    steps_below = max(0, cc_ts_tier - rec_tier)
    return steps_below * _QUALITY_PENALTY_PER_STEP


def main() -> int:
    # ------------------------------------------------------------------
    # Seed ε-greedy from eval-triggered observations (if file exists).
    # ------------------------------------------------------------------
    if _EVAL_OBS_PATH.exists():
        epsilon_greedy.load_observations(str(_EVAL_OBS_PATH))
    rng = random.Random(20260509)
    epsilon_greedy.set_rng(rng)

    # ------------------------------------------------------------------
    # Load dispatch trace.
    # ------------------------------------------------------------------
    if not _DECISIONS_PATH.exists():
        print(f"ERROR: {_DECISIONS_PATH} not found", file=sys.stderr)
        return 1

    records: list[dict] = []
    with open(_DECISIONS_PATH) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"WARN: skipping malformed line: {exc}", file=sys.stderr)

    if not records:
        print("ERROR: no records loaded", file=sys.stderr)
        return 1

    n_total = len(records)

    # ------------------------------------------------------------------
    # Accumulate per-policy stats.
    # ------------------------------------------------------------------
    # Each policy entry: {"cost": float, "tiers": [int, ...], "quality_sum": float}
    policies: dict[str, dict] = {
        "cc-ts":          {"cost": 0.0, "tiers": [], "quality_sum": 0.0},
        "static-fm":      {"cost": 0.0, "tiers": [], "quality_sum": 0.0},
        "epsilon-greedy": {"cost": 0.0, "tiers": [], "quality_sum": 0.0},
        "opus-default":   {"cost": 0.0, "tiers": [], "quality_sum": 0.0},
    }

    for r in records:
        agent = r.get("agent", "")
        shape = r.get("shape", "")
        cc_tier = int(r.get("recommended_tier", 1))

        choices = {
            "cc-ts":          cc_tier,
            "static-fm":      static_frontmatter.select(agent, shape),
            "epsilon-greedy": epsilon_greedy.select(agent, shape),
            "opus-default":   opus_default.select(agent, shape),
        }

        for name, tier in choices.items():
            p = policies[name]
            p["cost"] += _dispatch_cost(tier)
            p["tiers"].append(tier)
            penalty = _quality_penalty(tier, cc_tier)
            # cc-ts has zero penalty by definition (baseline = 1.0 per call)
            p["quality_sum"] += 1.0 - penalty

    # cc-ts total quality = n_total (1.0 per call; penalty = 0 vs itself)
    cc_ts_total_quality = policies["cc-ts"]["quality_sum"]

    # ------------------------------------------------------------------
    # Write CSV.
    # ------------------------------------------------------------------
    _OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "policy", "total_cost_usd",
            "n_haiku", "n_sonnet", "n_opus",
            "est_quality_score", "vs_cc_ts_pct",
        ])
        for name, p in policies.items():
            tiers = p["tiers"]
            n_h = tiers.count(0)
            n_s = tiers.count(1)
            n_o = tiers.count(2)
            total_cost = p["cost"]
            q_score = p["quality_sum"] / n_total  # normalised per-dispatch avg
            # vs_cc_ts_pct: positive = cheaper than cc-ts
            cc_ts_cost = policies["cc-ts"]["cost"]
            vs_pct = (cc_ts_cost - total_cost) / cc_ts_cost * 100.0 if cc_ts_cost > 0 else 0.0
            w.writerow([
                name,
                f"{total_cost:.4f}",
                n_h, n_s, n_o,
                f"{q_score:.4f}",
                f"{vs_pct:.2f}",
            ])

    # ------------------------------------------------------------------
    # Print summary to stdout.
    # ------------------------------------------------------------------
    print(f"Replayed {n_total} dispatch records against 4 policies.")
    print(f"Output written to: {_OUTPUT_CSV}")
    print()
    print(f"{'Policy':<20} {'Cost (USD)':>12} {'Haiku':>6} {'Sonnet':>7} {'Opus':>6} {'Quality':>9} {'vs cc-ts':>10}")
    print("-" * 75)
    for name, p in policies.items():
        tiers = p["tiers"]
        cost  = p["cost"]
        q     = p["quality_sum"] / n_total
        cc_ts_cost = policies["cc-ts"]["cost"]
        vs    = (cc_ts_cost - cost) / cc_ts_cost * 100.0 if cc_ts_cost > 0 else 0.0
        print(f"{name:<20} {cost:>12.4f} {tiers.count(0):>6} {tiers.count(1):>7} {tiers.count(2):>6} {q:>9.4f} {vs:>9.2f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
