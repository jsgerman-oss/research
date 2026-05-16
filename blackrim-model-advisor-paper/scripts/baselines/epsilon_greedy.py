"""
epsilon_greedy.py — ε-greedy bandit baseline policy.

At each dispatch the policy:
  - With probability ε (default 0.10): explores by sampling a tier
    uniformly at random from {haiku, sonnet, opus}.
  - With probability 1-ε: exploits by picking the tier with the
    highest empirical success rate in the same (shape, tier) bucket.

Success rates are seeded from `eval-triggered-observations.jsonl` when
that file is provided (using the shape/tier/success fields from eval
observations).  If no matching observations exist for a (shape, tier)
pair, the policy uses a uniform Laplace-smoothed prior of 0.5.

Parameters
----------
epsilon : float
    Exploration probability.  The paper uses ε = 0.10 (see §A hyperparams).
rng : random.Random
    Caller-supplied RNG for reproducibility.  Default is seeded from the
    paper's master seed (20260509).

API
---
All baseline modules expose the same two-argument `select(agent, shape)`
function.  ε-greedy additionally exposes `load_observations` to ingest
the eval-triggered file before replay begins.

Tier encoding
-------------
    0 = haiku, 1 = sonnet, 2 = opus
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Optional

_TIERS = [0, 1, 2]
_EPSILON: float = 0.10
_MASTER_SEED: int = 20260509

# Per-(shape, tier) accumulated (success_count, total_count) for exploitation.
# Keys: (shape: str, tier: int) → [successes, total]
_obs: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])

# Module-level RNG (seeded once at import; callers can replace via set_rng).
_rng: random.Random = random.Random(_MASTER_SEED)


def set_rng(rng: random.Random) -> None:
    """Replace the module-level RNG (used by replay.py for reproducibility)."""
    global _rng  # noqa: PLW0603
    _rng = rng


def load_observations(path: str) -> None:
    """Seed per-(shape, tier) success rates from an eval-observations file.

    The file is expected to have one JSONL record per line with at minimum:
        { "agent": "...", "shape": "...", "tier": <int>, "success": <bool> }

    Observations are accumulated additively, so this function can be called
    multiple times (e.g. in a streaming scenario).
    """
    import json

    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            shape = str(r.get("shape", ""))
            tier = r.get("tier")
            if tier is None or shape == "":
                continue
            key = (shape, int(tier))
            _obs[key][1] += 1
            if r.get("success"):
                _obs[key][0] += 1


def _success_rate(shape: str, tier: int) -> float:
    """Laplace-smoothed empirical success rate for (shape, tier)."""
    s, n = _obs[(shape, tier)]
    # Laplace smoothing: add 1 pseudo-success, 2 pseudo-observations.
    return (s + 1) / (n + 2)


def select(agent: str, shape: str,  # noqa: ARG001  (agent unused)
           epsilon: float = _EPSILON,
           rng: Optional[random.Random] = None) -> int:
    """Return the ε-greedy tier for this (agent, shape) pair.

    Parameters
    ----------
    agent:
        Agent name — accepted for API compatibility but not used (the
        policy operates at the shape level only, consistent with the
        bandit literature where the context is the task shape).
    shape:
        Task-shape code used as the bandit arm context.
    epsilon:
        Exploration probability.  Defaults to 0.10 (paper's ε = 0.10).
    rng:
        Optional caller-supplied RNG.  Falls back to the module-level RNG.

    Returns
    -------
    int
        0 (haiku), 1 (sonnet), or 2 (opus).
    """
    _r = rng or _rng
    if _r.random() < epsilon:
        # Explore: uniform random tier.
        return _r.choice(_TIERS)
    # Exploit: tier with highest Laplace-smoothed success rate.
    return max(_TIERS, key=lambda t: _success_rate(shape, t))
