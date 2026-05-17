#!/usr/bin/env python3
"""
ablation-gate.py — ablation study isolating the conservative gate (Layer 2).

Both policies are replayed against the 96-fixture eval suite:

  cc-ts          : cheapest tier whose Beta-posterior LCB clears the
                   tolerance-class threshold τ; fallback opus if none.
                   This is the canonical Layer 2 conservative-gated rule.
  greedy-bayes   : cheapest tier whose Beta-posterior MEAN is the
                   maximum across tiers — pure Thompson-style point-
                   estimate decision with no LCB guard. NOT genuine Thompson
                   Sampling (which would sample from the posterior); see
                   research-cq0 for the full-TS comparator follow-up.

Cost is computed from the same prices and synthetic representative
token budget (1200 in / 400 out) as scripts/baselines/replay.py, then
normalised to opus-default cost for the same 96 fixtures.

Quality regression is measured as (opus-default pass rate − policy
pass rate) in percentage points, where opus-default's pass rate is
81/96 = 84.4% (see data/aggregated/quality-comparison.csv).

Output: data/aggregated/ablation-gate.csv
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PAPER_ROOT = _HERE.parent
_FIXTURES = _PAPER_ROOT / "data" / "raw" / "eval-fixtures.jsonl"
_OUT = _PAPER_ROOT / "data" / "aggregated" / "ablation-gate.csv"

TIER_RANK = {
    "claude-haiku-4-5":  0,
    "claude-sonnet-4-6": 1,
    "claude-opus-4-7":   2,
}
_TOL_THRESHOLD = {
    "Critical": 1.00,
    "Strict":   0.90,
    "Moderate": 0.66,
    "Lenient":  0.50,
}

# Prices and synthetic token budget (mirror scripts/baselines/replay.py)
_PRICES = {
    0: {"input": 0.25,  "output": 0.50},   # haiku
    1: {"input": 3.00,  "output": 6.00},   # sonnet
    2: {"input": 15.00, "output": 30.00},  # opus
}
_INPUT_TOKS = 1200
_OUTPUT_TOKS = 400


def _dispatch_cost(tier: int) -> float:
    p = _PRICES[tier]
    return (_INPUT_TOKS / 1e6) * p["input"] + (_OUTPUT_TOKS / 1e6) * p["output"]


def _beta_lcb(alpha: float, beta_: float) -> float:
    mean = alpha / (alpha + beta_)
    var = (alpha * beta_) / ((alpha + beta_) ** 2 * (alpha + beta_ + 1))
    sd = var ** 0.5
    return max(0.0, mean - 1.645 * sd)


def _load_fixtures():
    out = []
    with open(_FIXTURES) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _build_cell_matrix(fixtures):
    cells = defaultdict(lambda: defaultdict(list))
    for f in fixtures:
        key = (f["agent"], f["shape"])
        tier = TIER_RANK[f["tier"]]
        cells[key][tier].append((f["fixture_id"], f["verdict"] == "pass"))
    return cells


def _cell_pass_rate(rows):
    if not rows:
        return 0.0
    return sum(1 for _, p in rows if p) / len(rows)


def _gated_choose(cell_data, tol):
    """cc-ts in the convergence limit: cheapest tier whose empirical
    pass rate clears the tolerance threshold; fallback opus if none.
    Matches scripts/quality-replay.py for cross-section consistency."""
    tau = _TOL_THRESHOLD.get(tol, 0.66)
    for tier in (0, 1, 2):
        rows = cell_data.get(tier, [])
        if rows and _cell_pass_rate(rows) >= tau:
            return tier
    return 2


def _greedy_bayes_choose(cell_data):
    """Greedy-Bayes: cheapest tier whose posterior MEAN equals the
    per-cell maximum. Deterministic point-estimate decision; differs
    from genuine Thompson Sampling which would sample from each
    posterior and pick argmax sample (preserving exploration). See
    research-cq0 for the full-TS comparator follow-up."""
    best_mean = -1.0
    best_tier = 2
    for tier in (0, 1, 2):
        rows = cell_data.get(tier, [])
        if not rows:
            continue
        n_pass = sum(1 for _, p in rows if p)
        n_fail = len(rows) - n_pass
        mean = (1 + n_pass) / (2 + n_pass + n_fail)
        if mean > best_mean:
            best_mean = mean
            best_tier = tier
    return best_tier


def _replay(name, fixtures, cells, rng):
    """Return (outcomes, tier_counts, cost_total)."""
    outcomes = []
    tier_counts = {0: 0, 1: 0, 2: 0}
    cost = 0.0
    for f in fixtures:
        cell = (f["agent"], f["shape"])
        cell_data = cells[cell]
        if name == "cc-ts":
            chosen = _gated_choose(cell_data, f.get("tolerance_class"))
        elif name == "greedy-bayes":
            chosen = _greedy_bayes_choose(cell_data)
        elif name == "opus-default":
            chosen = 2
        else:
            raise ValueError(name)
        tier_counts[chosen] += 1
        cost += _dispatch_cost(chosen)
        rows = cell_data.get(chosen, [])
        if not rows:
            outcomes.append(False)
            continue
        match = next(((fid, ok) for fid, ok in rows if fid == f["fixture_id"]), None)
        if match is None:
            match = rng.choice(rows)
        outcomes.append(match[1])
    return outcomes, tier_counts, cost


def main():
    fixtures = _load_fixtures()
    cells = _build_cell_matrix(fixtures)

    rng = random.Random(20260517)
    o_opus, _, c_opus = _replay("opus-default", fixtures, cells, rng)
    o_ccts, tc_ccts, c_ccts = _replay("cc-ts", fixtures, cells, rng)
    o_ung, tc_ung, c_ung = _replay("greedy-bayes", fixtures, cells, rng)

    n = len(fixtures)
    pass_opus = sum(o_opus) / n
    pass_ccts = sum(o_ccts) / n
    pass_ung = sum(o_ung) / n

    rows = [
        {
            "policy": "cc-ts",
            "cost_norm": c_ccts / c_opus,
            "cost_savings_pct": (c_opus - c_ccts) / c_opus * 100.0,
            "pass_rate": pass_ccts,
            "quality_regression_pp": (pass_opus - pass_ccts) * 100.0,
            "n_haiku": tc_ccts[0],
            "n_sonnet": tc_ccts[1],
            "n_opus": tc_ccts[2],
        },
        {
            "policy": "greedy-bayes",
            "cost_norm": c_ung / c_opus,
            "cost_savings_pct": (c_opus - c_ung) / c_opus * 100.0,
            "pass_rate": pass_ung,
            "quality_regression_pp": (pass_opus - pass_ung) * 100.0,
            "n_haiku": tc_ung[0],
            "n_sonnet": tc_ung[1],
            "n_opus": tc_ung[2],
        },
    ]

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "policy", "cost_norm", "cost_savings_pct", "pass_rate",
            "quality_regression_pp", "n_haiku", "n_sonnet", "n_opus",
        ])
        for r in rows:
            w.writerow([
                r["policy"],
                f"{r['cost_norm']:.4f}",
                f"{r['cost_savings_pct']:.2f}",
                f"{r['pass_rate']:.4f}",
                f"{r['quality_regression_pp']:.2f}",
                r["n_haiku"], r["n_sonnet"], r["n_opus"],
            ])
    print(f"output: {_OUT}")
    print(f"{'policy':<18}{'cost-norm':>12}{'save%':>10}{'pass':>10}{'Δreg pp':>10}{'  h/s/o':>14}")
    for r in rows:
        print(f"{r['policy']:<18}"
              f"{r['cost_norm']:>12.4f}{r['cost_savings_pct']:>10.2f}"
              f"{r['pass_rate']:>10.4f}{r['quality_regression_pp']:>10.2f}"
              f"   {r['n_haiku']}/{r['n_sonnet']}/{r['n_opus']}")


if __name__ == "__main__":
    main()
