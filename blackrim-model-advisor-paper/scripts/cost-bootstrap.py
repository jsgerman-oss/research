#!/usr/bin/env python3
"""
cost-bootstrap.py — bootstrap 95% CIs for per-policy normalised cost over
the 335-record advisor-decisions trace. Emits CSV consumed by
figures/cost-comparison.tex.

Method
------
For each of 1000 bootstrap iterations: resample the 335 dispatch records
with replacement; compute each policy's total cost on the resample; divide
by opus-default's cost on the SAME resample. Take 2.5/97.5 percentiles
of the resulting per-policy normalised-cost distribution.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PAPER_ROOT = _HERE.parent
_DECISIONS = _PAPER_ROOT / "data" / "raw" / "advisor-decisions.jsonl"
_OUT = _PAPER_ROOT / "data" / "aggregated" / "cost-bootstrap.csv"

# Make sibling baselines importable.
sys.path.insert(0, str(_HERE / "baselines"))
sys.path.insert(0, str(_HERE))
import static_frontmatter
import epsilon_greedy
import opus_default

_PRICES = {
    0: {"input": 0.25,  "output": 0.50},
    1: {"input": 3.00,  "output": 6.00},
    2: {"input": 15.00, "output": 30.00},
}
_IN, _OUT_T = 1200, 400


def _cost(tier):
    p = _PRICES[tier]
    return (_IN / 1e6) * p["input"] + (_OUT_T / 1e6) * p["output"]


def _load_decisions():
    out = []
    with open(_DECISIONS) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _policy_choices(records, rng):
    """Return dict policy->list[tier] for the records."""
    return {
        "cc-ts":          [int(r["recommended_tier"]) for r in records],
        "static-fm":      [static_frontmatter.select(r.get("agent",""), r.get("shape","")) for r in records],
        "epsilon-greedy": [epsilon_greedy.select(r.get("agent",""), r.get("shape","")) for r in records],
        "opus-default":   [2] * len(records),
    }


def main():
    records = _load_decisions()
    n = len(records)
    rng = random.Random(20260517)

    # Seed epsilon_greedy as in replay.py
    obs_path = _PAPER_ROOT / "data" / "raw" / "eval-triggered-observations.jsonl"
    if obs_path.exists():
        epsilon_greedy.load_observations(str(obs_path))
    epsilon_greedy.set_rng(rng)

    # Precompute per-record tier choices (deterministic for non-ε policies).
    base_choices = _policy_choices(records, rng)
    # Convert to per-record cost vectors per policy.
    cost_vec = {p: [_cost(t) for t in base_choices[p]] for p in base_choices}

    iters = 1000
    boot = {p: [] for p in cost_vec}
    for _ in range(iters):
        idxs = [rng.randrange(n) for _ in range(n)]
        opus_total = sum(cost_vec["opus-default"][i] for i in idxs)
        for p in cost_vec:
            ptot = sum(cost_vec[p][i] for i in idxs)
            boot[p].append(ptot / opus_total if opus_total > 0 else 0.0)

    rows = []
    for p in ("opus-default", "static-fm", "epsilon-greedy", "cc-ts"):
        vals = sorted(boot[p])
        point = sum(cost_vec[p]) / sum(cost_vec["opus-default"])
        lo = vals[int(0.025 * iters)]
        hi = vals[int(0.975 * iters)]
        rows.append((p, point, lo, hi))

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["policy", "cost_norm", "cost_norm_lo95", "cost_norm_hi95"])
        for r in rows:
            w.writerow([r[0], f"{r[1]:.4f}", f"{r[2]:.4f}", f"{r[3]:.4f}"])
    print(f"wrote {_OUT}")
    for r in rows:
        print(f"  {r[0]:<18}{r[1]:>8.4f}  [{r[2]:.4f}, {r[3]:.4f}]")


if __name__ == "__main__":
    main()
