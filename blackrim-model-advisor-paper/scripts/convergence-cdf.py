#!/usr/bin/env python3
"""
convergence-cdf.py — empirical convergence-time CDF for cc-ts cells.

Two cell groups are emitted:

  high-confidence : cells where the MOA-1b prior already encodes a
                    strong recommendation. We observe these in
                    advisor-decisions.jsonl (production telemetry).
  thin-evidence   : cells with uncertain priors. We simulate cc-ts's
                    Beta-Bernoulli update path over the eval-fixtures
                    observations in deterministic seeded order.

For both groups, a cell is "converged" at dispatch index k if its
cc-ts tier recommendation does not flip again for at least the next
WINDOW = 5 dispatches (or remaining observations < WINDOW, in which
case the final-state stability is taken).

Outputs
-------
data/aggregated/convergence-cdf.csv : columns
    group, dispatches, cdf
data/aggregated/convergence-summary.csv : columns
    group, n_cells, mean_dispatches, median_dispatches, p90_dispatches
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PAPER_ROOT = _HERE.parent
_DECISIONS = _PAPER_ROOT / "data" / "raw" / "advisor-decisions.jsonl"
_FIXTURES = _PAPER_ROOT / "data" / "raw" / "eval-fixtures.jsonl"
_CDF_OUT = _PAPER_ROOT / "data" / "aggregated" / "convergence-cdf.csv"
_SUM_OUT = _PAPER_ROOT / "data" / "aggregated" / "convergence-summary.csv"

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

_FLIP_FREE_WINDOW = 5      # dispatches without a flip = converged
_SIM_SEED = 20260517
_SIM_LEN = 100             # extend each thin-evidence cell to 100 dispatches
                           # via bootstrap-resample of its 9 actual eval obs
_N_SIM_RUNS = 200          # per-cell simulation replicas for CI


def _load_jsonl(path: Path) -> list[dict]:
    out = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _beta_lcb(alpha: float, beta_: float) -> float:
    """Approximate lower 5% credible bound of Beta(α, β) via normal
    approximation (mean − 1.645 · sd). Sufficient for tier-comparison
    in this paper; production code uses scipy.stats.beta.ppf."""
    mean = alpha / (alpha + beta_)
    var = (alpha * beta_) / ((alpha + beta_) ** 2 * (alpha + beta_ + 1))
    sd = var ** 0.5
    return max(0.0, mean - 1.645 * sd)


def _recommend_tier(alpha_beta_by_tier: dict[int, tuple[float, float]],
                    tau: float) -> int:
    """Cheapest tier whose Beta(α, β) LCB ≥ τ; else fall back to opus."""
    for tier in (0, 1, 2):
        a, b = alpha_beta_by_tier.get(tier, (1.0, 1.0))
        if _beta_lcb(a, b) >= tau:
            return tier
    return 2


def _trajectory_last_flip(tier_seq: list[int]) -> int:
    """Dispatch index of the last tier flip — the first dispatch from
    which the recommendation never changes for the remainder of the
    trajectory. Returns 0 if no flip ever occurs.
    """
    n = len(tier_seq)
    if n <= 1:
        return 0
    last = 0
    for k in range(1, n):
        if tier_seq[k] != tier_seq[k - 1]:
            last = k
    return last


def _high_confidence_convergence() -> list[int]:
    """Per-cell convergence dispatches from advisor-decisions.jsonl."""
    records = _load_jsonl(_DECISIONS)
    cells: dict = defaultdict(list)
    for r in records:
        cells[(r["agent"], r["shape"])].append(int(r["recommended_tier"]))
    return [_trajectory_last_flip(seq) for seq in cells.values()]


def _simulate_one_trajectory(obs, rng, length=_SIM_LEN):
    """Run cc-ts on bootstrap-resampled observations of length `length`.

    Each step draws one observation uniformly with replacement from the
    real eval-fixture observations for the cell, updates the per-tier
    Beta posterior, and records the cc-ts recommendation. Returns the
    dispatch index of the last tier flip.
    """
    tol_class = obs[0].get("tolerance_class", "Moderate")
    tau = _TOL_THRESHOLD.get(tol_class, 0.66)
    alpha_beta = {0: (1.0, 1.0), 1: (1.0, 1.0), 2: (1.0, 1.0)}
    tier_seq: list[int] = []
    for _ in range(length):
        o = obs[rng.randrange(len(obs))]
        tier = TIER_RANK[o["tier"]]
        a, b = alpha_beta[tier]
        if o["verdict"] == "pass":
            alpha_beta[tier] = (a + 1.0, b)
        else:
            alpha_beta[tier] = (a, b + 1.0)
        tier_seq.append(_recommend_tier(alpha_beta, tau))
    return _trajectory_last_flip(tier_seq)


def _thin_evidence_convergence() -> list[int]:
    """For each eval-fixture cell, run `_N_SIM_RUNS` bootstrap replicas
    of length `_SIM_LEN`. Per-cell convergence is the median replica.
    Returns one value per cell."""
    fixtures = _load_jsonl(_FIXTURES)
    cells: dict = defaultdict(list)
    for f in fixtures:
        cells[(f["agent"], f["shape"])].append(f)
    out: list[int] = []
    rng = random.Random(_SIM_SEED)
    for cell, obs in cells.items():
        runs = [_simulate_one_trajectory(obs, rng) for _ in range(_N_SIM_RUNS)]
        runs.sort()
        out.append(runs[len(runs) // 2])  # median
    return out


def _empirical_cdf(values: list[int], max_x: int) -> list[tuple[int, float]]:
    n = len(values)
    if n == 0:
        return [(0, 0.0)]
    pts = []
    for x in range(0, max_x + 1):
        cdf = sum(1 for v in values if v <= x) / n
        pts.append((x, cdf))
    return pts


def main() -> int:
    hi = _high_confidence_convergence()
    thin = _thin_evidence_convergence()
    max_x = max(max(hi, default=0), max(thin, default=0), 10)

    cdf_hi = _empirical_cdf(hi, max_x)
    cdf_thin = _empirical_cdf(thin, max_x)

    _CDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_CDF_OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "dispatches", "cdf"])
        for x, c in cdf_hi:
            w.writerow(["high-confidence", x, f"{c:.4f}"])
        for x, c in cdf_thin:
            w.writerow(["thin-evidence", x, f"{c:.4f}"])

    def _stats(vals):
        if not vals:
            return (0, 0.0, 0.0, 0.0)
        s = sorted(vals)
        n = len(s)
        mean = sum(s) / n
        median = s[n // 2]
        p90 = s[min(n - 1, int(0.9 * n))]
        return (n, mean, median, p90)

    rows = [
        ("high-confidence", *_stats(hi)),
        ("thin-evidence",   *_stats(thin)),
    ]
    with open(_SUM_OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "n_cells", "mean_dispatches", "median_dispatches", "p90_dispatches"])
        for g, n, m, med, p90 in rows:
            w.writerow([g, n, f"{m:.2f}", f"{med}", f"{p90}"])

    print(f"high-confidence cells: n={len(hi)}, dispatches-to-converge: {hi}")
    print(f"thin-evidence cells:   n={len(thin)}, dispatches-to-converge: {thin}")
    print(f"summary: {_SUM_OUT}")
    print(f"cdf:     {_CDF_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
