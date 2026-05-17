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
from typing import Optional

_HERE = Path(__file__).resolve().parent
_PAPER_ROOT = _HERE.parent
_DECISIONS = _PAPER_ROOT / "data" / "raw" / "advisor-decisions.jsonl"
_FIXTURES = _PAPER_ROOT / "data" / "raw" / "eval-fixtures.jsonl"
_CDF_OUT = _PAPER_ROOT / "data" / "aggregated" / "convergence-cdf.csv"
_SUM_OUT = _PAPER_ROOT / "data" / "aggregated" / "convergence-summary.csv"
_PRIORS = _PAPER_ROOT / "data" / "aggregated" / "moa1b-cells.json"

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


def _load_moa1b_priors() -> dict:
    """Load MOA-1b per-cell prior pseudocounts.

    Returns dict keyed (agent_lower, shape) -> {tier: (alpha, beta)} for
    cells listed in moa1b-cells.json. Conversion follows the spec in the
    file header: baseline_tier gets Beta(alpha=max(1, round(conf/5)),
    beta=max(1, round((100-conf)/5))); non-baseline tiers start at
    Beta(1, 1). Cells not in the file fall back to flat priors per tier.
    """
    if not _PRIORS.exists():
        return {}
    import json as _json
    raw = _json.loads(_PRIORS.read_text())
    out: dict = {}
    for cell in raw.get("cells", []):
        agent = cell["agent"].lower()
        shape = cell["shape"]
        baseline_tier = cell["baseline_tier"]
        conf = cell["confidence_pct"]
        a = max(1.0, round(conf / 5.0))
        b = max(1.0, round((100 - conf) / 5.0))
        ab = {0: (1.0, 1.0), 1: (1.0, 1.0), 2: (1.0, 1.0)}
        ab[baseline_tier] = (a, b)
        out[(agent, shape)] = ab
    return out


def _prior_for(cell: tuple, priors: dict) -> dict:
    """Return the per-tier Beta priors for `cell`; fall back to uniform
    Beta(1, 1) on each tier when the cell is not in the prior table."""
    return priors.get(cell, {0: (1.0, 1.0), 1: (1.0, 1.0), 2: (1.0, 1.0)})


def _beta_lcb(alpha: float, beta_: float) -> float:
    """Exact lower 5%% credible bound of Beta(α, β) via scipy.stats.
    Replaces the normal-approximation Wald LCB used in earlier
    revisions; the exact bound is materially different at small
    counts (e.g. Beta(2,1) Wald = 0.17 vs exact = 0.224)."""
    from scipy.stats import beta as _beta
    return float(_beta.ppf(0.05, alpha, beta_))


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


def _simulate_one_trajectory(obs, rng, prior, length=_SIM_LEN):
    """Run cc-ts on bootstrap-resampled observations of length `length`,
    seeded from the supplied per-tier prior pseudocounts.

    Each step draws one observation uniformly with replacement from the
    real eval-fixture observations for the cell, updates the per-tier
    Beta posterior, and records the cc-ts recommendation. Returns the
    dispatch index of the last tier flip.
    """
    tol_class = obs[0].get("tolerance_class", "Moderate")
    tau = _TOL_THRESHOLD.get(tol_class, 0.66)
    alpha_beta = {t: (a, b) for t, (a, b) in prior.items()}
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


def _thin_evidence_convergence(use_priors: bool = True) -> tuple[list[int], list[bool]]:
    """For each eval-fixture cell, run `_N_SIM_RUNS` bootstrap replicas
    of length `_SIM_LEN`. Per-cell convergence is the median replica.
    Returns (values, has_prior_flags) — one entry per cell."""
    fixtures = _load_jsonl(_FIXTURES)
    cells: dict = defaultdict(list)
    for f in fixtures:
        cells[(f["agent"], f["shape"])].append(f)
    priors = _load_moa1b_priors() if use_priors else {}
    out: list[int] = []
    has_prior: list[bool] = []
    rng = random.Random(_SIM_SEED)
    for cell, obs in cells.items():
        prior = _prior_for(cell, priors)
        runs = [_simulate_one_trajectory(obs, rng, prior) for _ in range(_N_SIM_RUNS)]
        runs.sort()
        out.append(runs[len(runs) // 2])
        has_prior.append(cell in priors)
    return out, has_prior


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
    thin_flat, _ = _thin_evidence_convergence(use_priors=False)
    thin_informed, has_prior = _thin_evidence_convergence(use_priors=True)
    max_x = max(max(hi, default=0), max(thin_flat, default=0),
                max(thin_informed, default=0), 10)

    cdf_hi = _empirical_cdf(hi, max_x)
    cdf_thin_flat = _empirical_cdf(thin_flat, max_x)
    cdf_thin_informed = _empirical_cdf(thin_informed, max_x)

    _CDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_CDF_OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "dispatches", "cdf"])
        for x, c in cdf_hi:
            w.writerow(["high-confidence", x, f"{c:.4f}"])
        for x, c in cdf_thin_flat:
            w.writerow(["thin-evidence-flat", x, f"{c:.4f}"])
        for x, c in cdf_thin_informed:
            w.writerow(["thin-evidence-informed", x, f"{c:.4f}"])

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
        ("high-confidence",          *_stats(hi)),
        ("thin-evidence-flat",       *_stats(thin_flat)),
        ("thin-evidence-informed",   *_stats(thin_informed)),
    ]
    with open(_SUM_OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "n_cells", "mean_dispatches", "median_dispatches", "p90_dispatches"])
        for g, n, m, med, p90 in rows:
            w.writerow([g, n, f"{m:.2f}", f"{med}", f"{p90}"])

    print(f"high-confidence cells: n={len(hi)}, dispatches-to-converge: {hi}")
    print(f"thin-evidence flat priors:     {thin_flat}")
    print(f"thin-evidence MOA-1b priors:   {thin_informed}")
    print(f"prior coverage: {sum(has_prior)}/{len(has_prior)} cells")
    print(f"summary: {_SUM_OUT}")
    print(f"cdf:     {_CDF_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
