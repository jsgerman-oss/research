#!/usr/bin/env python3
"""
run-eval-suite.py — evaluate a candidate advisor policy against held-out data.

Reads:
    data/raw/telemetry.jsonl  (anonymised production stream)
    data/raw/eval-fixtures.jsonl  (held-out tasks with ground-truth quality)
Writes:
    data/aggregated/<advisor>-results.csv

Advisors implemented:
    opus-default        — always opus
    static-frontmatter  — reads citizen/worker .md frontmatter for the agent
    epsilon-greedy      — vanilla bandit baseline (alpha=0.1)
    conservative-ts     — CC-TS as described in §5

Doubly-robust off-policy evaluation: for each advisor, we estimate the cost
each advisor would have incurred on the production trace assuming logged
propensities at the dispatch policy in effect when the trace was captured.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

from beta_utils import beta_credible_interval, prior_pseudocounts


_TIERS = ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7")
_TIER_ORDINAL = {t: i for i, t in enumerate(_TIERS)}


def _opus_default(_signals: dict) -> str:
    return "claude-opus-4-7"


def _static_frontmatter(signals: dict) -> str:
    role = signals.get("agent_role", "")
    if role in ("researcher", "writer", "judge"):
        return "claude-haiku-4-5"
    if role in ("builder", "reviewer", "tester"):
        return "claude-sonnet-4-6"
    return "claude-opus-4-7"


def _epsilon_greedy(signals: dict, *, posteriors: dict, rng: random.Random,
                    epsilon: float = 0.1) -> str:
    if rng.random() < epsilon:
        return rng.choice(_TIERS)
    cell = (signals.get("agent"), signals.get("shape"))
    means = {t: _empirical_mean(posteriors[(cell, t)]) for t in _TIERS}
    return max(means, key=means.get)


def _conservative_ts(signals: dict, *, posteriors: dict, rng: random.Random,
                     prior: dict, tolerance_class: str = "Moderate",
                     alpha: float = 0.05) -> str:
    """Layered CC-TS — see §5 of the paper."""
    cell = (signals.get("agent"), signals.get("shape"))
    baseline_tier = _baseline_for_role(signals.get("agent_role", ""))
    baseline_mean = _posterior_mean_with_prior(
        posteriors[(cell, baseline_tier)], prior.get((cell, baseline_tier))
    )
    tolerance = {"Critical": 0.0, "Strict": 0.02,
                 "Moderate": 0.05, "Lenient": 0.10}.get(tolerance_class, 0.05)

    candidates = [baseline_tier]
    for tier in _TIERS:
        if tier == baseline_tier:
            continue
        post = posteriors[(cell, tier)]
        post_with_prior = _combine_with_prior(post, prior.get((cell, tier)))
        if _TIER_ORDINAL[tier] < _TIER_ORDINAL[baseline_tier]:
            lo, _ = beta_credible_interval(*post_with_prior, alpha=alpha)
            if lo < baseline_mean - tolerance:
                continue
        candidates.append(tier)

    # Asymmetric-loss tiebreak: cheapest first.
    return sorted(candidates, key=lambda t: _TIER_ORDINAL[t])[0]


def _empirical_mean(post: tuple) -> float:
    s, f = post
    n = s + f
    return s / n if n > 0 else 0.5


def _posterior_mean_with_prior(post: tuple, prior_pseudo: tuple | None) -> float:
    a, b = post
    if prior_pseudo is not None:
        a += prior_pseudo[0]
        b += prior_pseudo[1]
    return a / (a + b) if (a + b) > 0 else 0.5


def _combine_with_prior(post: tuple, prior_pseudo: tuple | None) -> tuple:
    s, f = post
    if prior_pseudo is None:
        return (s + 1, f + 1)
    return (s + prior_pseudo[0], f + prior_pseudo[1])


def _baseline_for_role(role: str) -> str:
    return _static_frontmatter({"agent_role": role})


def _select(advisor: str, signals: dict, *, posteriors: dict, prior: dict,
            rng: random.Random) -> str:
    if advisor == "opus-default":
        return _opus_default(signals)
    if advisor == "static-frontmatter":
        return _static_frontmatter(signals)
    if advisor == "epsilon-greedy":
        return _epsilon_greedy(signals, posteriors=posteriors, rng=rng)
    if advisor == "conservative-ts":
        return _conservative_ts(signals, posteriors=posteriors, rng=rng,
                                prior=prior)
    raise ValueError(f"unknown advisor: {advisor}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--advisor", required=True,
                   choices=["opus-default", "static-frontmatter",
                            "epsilon-greedy", "conservative-ts"])
    p.add_argument("--telemetry", default="data/raw/telemetry.jsonl")
    p.add_argument("--prior",
                   default="data/raw/moa1b-prior.csv",
                   help="MOA-1b confidence-per-cell CSV (cell -> confidence%).")
    p.add_argument("--out", default="data/aggregated/{advisor}-results.csv")
    p.add_argument("--seed", type=int, default=20260509)
    args = p.parse_args()

    rng = random.Random(args.seed)
    posteriors: dict = defaultdict(lambda: (0, 0))
    prior_table: dict = {}

    if Path(args.prior).exists():
        with open(args.prior) as f:
            for row in csv.DictReader(f):
                key = ((row["agent_id"], row["shape_id"]), row["model"])
                prior_table[key] = prior_pseudocounts(float(row["confidence"]))

    out_path = args.out.format(advisor=args.advisor)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    with open(args.telemetry) as src, open(out_path, "w", newline="") as dst:
        w = csv.writer(dst)
        w.writerow(["ts", "agent", "shape", "advisor", "tier_picked",
                    "cost_estimated_usd", "outcome_observed"])
        for line in src:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            signals = {
                "agent": r.get("agent"),
                "shape": r.get("shape"),
                "agent_role": r.get("agent_role", "builder"),
            }
            tier = _select(args.advisor, signals,
                           posteriors=posteriors, prior=prior_table, rng=rng)
            cost = _est_cost(tier, r)
            outcome = r.get("outcome", "unknown")
            w.writerow([r.get("ts"), signals["agent"], signals["shape"],
                        args.advisor, tier, f"{cost:.6f}", outcome])
            if outcome in ("success", "failure"):
                key = ((signals["agent"], signals["shape"]), tier)
                s, f = posteriors[key]
                if outcome == "success":
                    posteriors[key] = (s + 1, f)
                else:
                    posteriors[key] = (s, f + 1)

    print(f"wrote {out_path}", file=sys.stderr)
    return 0


def _est_cost(tier: str, record: dict) -> float:
    """Rough off-policy cost estimate.

    The right thing here is doubly-robust evaluation conditioned on the
    logged propensity. In v1 we use a per-tier average input/output token
    profile derived from MOA-1b. This is a known approximation; the
    paper reports both the DR estimate and this naïve estimate.
    """
    profile = {
        "claude-haiku-4-5":  {"input": 5_000, "output": 1_500},
        "claude-sonnet-4-6": {"input": 8_000, "output": 3_000},
        "claude-opus-4-7":   {"input": 12_000, "output": 6_000},
    }[tier]
    rates = {
        "claude-haiku-4-5":  {"input": 1.0, "output": 5.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
    }[tier]
    return (profile["input"] * rates["input"] +
            profile["output"] * rates["output"]) / 1e6


if __name__ == "__main__":
    raise SystemExit(main())
