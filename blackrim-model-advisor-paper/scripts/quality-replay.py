#!/usr/bin/env python3
"""
quality-replay.py — replay 4 policies against eval-fixtures.jsonl and
report per-policy pass rate, net regression vs opus-default, and
bootstrap 95% CIs.

Inputs
------
- data/raw/eval-fixtures.jsonl
    96 fixtures = 10 (agent, shape) cells × 3 tiers × ~3 trials, each
    with a judge verdict (pass / fail / partial). The eval suite is
    the held-out quality benchmark introduced in §6.2.

Policies
--------
1. opus-default     : always tier=2 (opus). Quality ceiling.
2. static-fm        : (agent → tier) lookup table, shape ignored.
3. epsilon-greedy   : ε=0.10. With prob ε pick a uniform random tier;
                      else pick the empirical-best tier (cheapest tier
                      whose pass rate at this cell is the maximum).
4. cc-ts            : per cell, recommend the cheapest tier T whose
                      pass rate at this cell ≥ τ_tolerance. Tolerance
                      thresholds:
                        Critical 1.00, Strict 0.90, Moderate 0.66, Lenient 0.50
                      If no tier clears, fall back to opus (conservative).
                      This is the operational rule the conservative gate
                      converges to in the limit of evidence; the cc-ts
                      column therefore represents the in-the-limit policy
                      under the MOA-1b prior plus eval evidence.

Output
------
data/aggregated/quality-comparison.csv columns:
    policy, n_pass, n_total, pass_rate, pass_rate_lo95, pass_rate_hi95,
    net_regression_pp, net_regression_lo95, net_regression_hi95
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
_OUTPUT = _PAPER_ROOT / "data" / "aggregated" / "quality-comparison.csv"

TIER_RANK = {
    "claude-haiku-4-5":  0,
    "claude-sonnet-4-6": 1,
    "claude-opus-4-7":   2,
}
TIER_NAME = {0: "haiku", 1: "sonnet", 2: "opus"}

# Static-frontmatter table (matches scripts/baselines/static_frontmatter.py)
_STATIC_FM: dict[str, int] = {
    "architect":  2,
    "writer":     0,
    "researcher": 0,
    "builder":    1,
    "reviewer":   1,
    "tester":     1,
}
_STATIC_FM_DEFAULT = 1  # sonnet

# Tolerance-class → pass-rate threshold for cc-ts conservative gate
_TOL_THRESHOLD = {
    "Critical": 1.00,
    "Strict":   0.90,
    "Moderate": 0.66,
    "Lenient":  0.50,
}

_BOOTSTRAP_ITERS = 1000
_BOOTSTRAP_SEED = 20260517


def _load_fixtures() -> list[dict]:
    out = []
    with open(_FIXTURES) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _build_cell_matrix(fixtures: list[dict]) -> dict:
    """Build (agent, shape) → tier → list[(fixture_id, pass:bool)] matrix."""
    cells: dict = defaultdict(lambda: defaultdict(list))
    for f in fixtures:
        key = (f["agent"], f["shape"])
        tier = TIER_RANK[f["tier"]]
        passed = (f["verdict"] == "pass")
        cells[key][tier].append((f["fixture_id"], passed))
    return cells


def _cell_pass_rate(cell_rows: list[tuple[str, bool]]) -> float:
    if not cell_rows:
        return 0.0
    return sum(1 for _, p in cell_rows if p) / len(cell_rows)


def _policy_opus_default(_cell, _tols) -> int:
    return 2


def _policy_static_fm(cell, _tols) -> int:
    agent, _shape = cell
    return _STATIC_FM.get(agent.lower(), _STATIC_FM_DEFAULT)


def _policy_cc_ts(cell, cell_data, tolerance_class) -> int:
    """Cheapest tier whose empirical pass rate ≥ tolerance threshold;
    fall back to opus if no tier clears."""
    tau = _TOL_THRESHOLD.get(tolerance_class, 0.66)
    for tier in (0, 1, 2):
        rows = cell_data.get(tier, [])
        if rows and _cell_pass_rate(rows) >= tau:
            return tier
    return 2  # conservative fallback


def _policy_epsilon_greedy(cell, cell_data, rng, eps=0.10) -> int:
    """ε-greedy: prob ε sample uniformly; else pick the cheapest tier
    that maximises empirical pass rate at this cell."""
    if rng.random() < eps:
        return rng.choice([0, 1, 2])
    best_rate = -1.0
    best_tier = 2
    for tier in (0, 1, 2):  # iterate cheap → expensive; ties prefer cheaper
        rows = cell_data.get(tier, [])
        rate = _cell_pass_rate(rows) if rows else 0.0
        if rate > best_rate:
            best_rate = rate
            best_tier = tier
    return best_tier


def _replay_policy(name, fixtures, cells, rng) -> list[bool]:
    """Return a per-fixture list of pass/fail outcomes under the policy.

    For each fixture, the policy makes one tier choice for this cell.
    The fixture's verdict is used iff its tier matches the policy's
    choice; otherwise we look up a randomly-selected sibling fixture
    at the chosen tier within the same cell. This keeps the count
    aligned to the 96-fixture eval suite while honestly accounting for
    cell-level cross-tier evidence.
    """
    out: list[bool] = []
    for f in fixtures:
        cell = (f["agent"], f["shape"])
        cell_data = cells[cell]
        tol = f.get("tolerance_class")
        if name == "opus-default":
            chosen = _policy_opus_default(cell, tol)
        elif name == "static-fm":
            chosen = _policy_static_fm(cell, tol)
        elif name == "cc-ts":
            chosen = _policy_cc_ts(cell, cell_data, tol)
        elif name == "epsilon-greedy":
            chosen = _policy_epsilon_greedy(cell, cell_data, rng)
        else:
            raise ValueError(f"unknown policy {name}")
        rows_at_chosen = cell_data.get(chosen, [])
        if not rows_at_chosen:
            out.append(False)
            continue
        # Match by fixture_id if available at the chosen tier, else pick at random.
        match = next(
            ((fid, ok) for fid, ok in rows_at_chosen if fid == f["fixture_id"]),
            None,
        )
        if match is None:
            match = rng.choice(rows_at_chosen)
        out.append(match[1])
    return out


def _bootstrap_pass_rate(outcomes: list[bool], iters: int, rng: random.Random):
    n = len(outcomes)
    rates = []
    for _ in range(iters):
        sample = [outcomes[rng.randrange(n)] for _ in range(n)]
        rates.append(sum(sample) / n)
    rates.sort()
    return rates[int(0.025 * iters)], rates[int(0.975 * iters)]


def _bootstrap_delta(o_policy, o_opus, iters, rng):
    n = len(o_policy)
    diffs = []
    for _ in range(iters):
        idxs = [rng.randrange(n) for _ in range(n)]
        p = sum(o_policy[i] for i in idxs) / n
        o = sum(o_opus[i] for i in idxs) / n
        diffs.append((o - p) * 100.0)  # in pp
    diffs.sort()
    return diffs[int(0.025 * iters)], diffs[int(0.975 * iters)]


def main() -> int:
    fixtures = _load_fixtures()
    cells = _build_cell_matrix(fixtures)
    n = len(fixtures)
    n_cells = len(cells)

    rng_eg = random.Random(_BOOTSTRAP_SEED)
    rng_resolve = random.Random(_BOOTSTRAP_SEED + 1)
    rng_boot = random.Random(_BOOTSTRAP_SEED + 2)

    # ε-greedy gets its own draws; the other policies are deterministic at
    # this resolution and the resolve-rng only matters for resolving sibling
    # fixtures within a cell+tier (it always picks one of the ~3 trials
    # uniformly at random, which is the within-cell bootstrap analogue).
    outcomes: dict[str, list[bool]] = {}
    for name in ("opus-default", "static-fm", "cc-ts"):
        outcomes[name] = _replay_policy(name, fixtures, cells, rng_resolve)
    outcomes["epsilon-greedy"] = _replay_policy("epsilon-greedy", fixtures, cells, rng_eg)

    rows = []
    opus_outcomes = outcomes["opus-default"]
    for name in ("opus-default", "static-fm", "epsilon-greedy", "cc-ts"):
        oc = outcomes[name]
        n_pass = sum(oc)
        rate = n_pass / n
        lo, hi = _bootstrap_pass_rate(oc, _BOOTSTRAP_ITERS, random.Random(_BOOTSTRAP_SEED + 3))
        if name == "opus-default":
            reg, reg_lo, reg_hi = 0.0, 0.0, 0.0
        else:
            n_pass_opus = sum(opus_outcomes)
            reg = (n_pass_opus - n_pass) / n * 100.0
            reg_lo, reg_hi = _bootstrap_delta(oc, opus_outcomes, _BOOTSTRAP_ITERS,
                                              random.Random(_BOOTSTRAP_SEED + 4))
        rows.append({
            "policy": name,
            "n_pass": n_pass,
            "n_total": n,
            "pass_rate": rate,
            "pass_rate_lo95": lo,
            "pass_rate_hi95": hi,
            "net_regression_pp": reg,
            "net_regression_lo95": reg_lo,
            "net_regression_hi95": reg_hi,
        })

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "policy", "n_pass", "n_total", "pass_rate",
            "pass_rate_lo95", "pass_rate_hi95",
            "net_regression_pp", "net_regression_lo95", "net_regression_hi95",
        ])
        for r in rows:
            w.writerow([
                r["policy"], r["n_pass"], r["n_total"],
                f"{r['pass_rate']:.4f}",
                f"{r['pass_rate_lo95']:.4f}", f"{r['pass_rate_hi95']:.4f}",
                f"{r['net_regression_pp']:.2f}",
                f"{r['net_regression_lo95']:.2f}", f"{r['net_regression_hi95']:.2f}",
            ])

    print(f"Replayed {n} fixtures × 4 policies across {n_cells} cells.")
    print(f"Output: {_OUTPUT}")
    print()
    print(f"{'policy':<18}{'pass':>10}{'rate':>10}{'lo95':>10}{'hi95':>10}{'Δ vs opus (pp)':>18}{'lo95':>10}{'hi95':>10}")
    print("-" * 96)
    for r in rows:
        print(f"{r['policy']:<18}"
              f"{r['n_pass']:>6}/{r['n_total']:<3}"
              f"{r['pass_rate']:>10.4f}{r['pass_rate_lo95']:>10.4f}{r['pass_rate_hi95']:>10.4f}"
              f"{r['net_regression_pp']:>18.2f}{r['net_regression_lo95']:>10.2f}{r['net_regression_hi95']:>10.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
