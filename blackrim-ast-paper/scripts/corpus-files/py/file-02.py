#!/usr/bin/env python3
"""
aggregate-by-shape.py — roll up data/raw/telemetry.jsonl into the
per-(agent, shape, model) cost-quality table that backs §6 of the paper.

Reads stdin (one normalised JSONL record per line as emitted by
pull-telemetry.py) and writes a CSV to stdout.

Output schema:
    agent_id, shape_id, model, provider, n_dispatches,
    cost_total_usd, cost_per_call_mean,
    success_rate, success_low_95, success_high_95
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from typing import Tuple

from beta_utils import beta_credible_interval, prior_pseudocounts  # noqa: F401

# Pricing — kept in step with internal/pricing/sheets/anthropic-public.toml.
# Keys are short canonical model IDs (post-Bedrock-normalisation).
_RATES = {
    # opus-4-7
    "claude-opus-4-7":  {"input": 15.0, "output": 75.0,
                         "c5m": 15.0, "c1h": 18.75, "cr": 1.50},
    # sonnet-4-6
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0,
                          "c5m": 3.0, "c1h": 3.75, "cr": 0.30},
    # haiku-4-5
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0,
                         "c5m": 1.0, "c1h": 1.25, "cr": 0.10},
}


def _cost(record: dict) -> float:
    rates = _RATES.get(record.get("model"))
    if rates is None:
        return 0.0
    cost = 0.0
    cost += (record.get("input_tokens") or 0) / 1e6 * rates["input"]
    cost += (record.get("output_tokens") or 0) / 1e6 * rates["output"]
    cost += (record.get("cache_creation_5m") or 0) / 1e6 * rates["c5m"]
    cost += (record.get("cache_creation_1h") or 0) / 1e6 * rates["c1h"]
    cost += (record.get("cache_read") or 0) / 1e6 * rates["cr"]
    return cost


def _outcome_to_q(o: str | None) -> int | None:
    if o == "success":
        return 1
    if o == "failure":
        return 0
    return None  # unobserved


def main() -> int:
    buckets: dict[Tuple[str, str, str, str], dict] = defaultdict(
        lambda: {"n": 0, "cost": 0.0, "n_obs": 0, "n_success": 0,
                 "provider": ""}
    )

    for line in sys.stdin:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (r.get("agent", ""), r.get("shape", ""),
               r.get("model", ""), r.get("provider", "anthropic"))
        b = buckets[key]
        b["n"] += 1
        b["cost"] += _cost(r)
        b["provider"] = key[3]
        q = _outcome_to_q(r.get("outcome"))
        if q is not None:
            b["n_obs"] += 1
            b["n_success"] += q

    w = csv.writer(sys.stdout)
    w.writerow([
        "agent_id", "shape_id", "model", "provider", "n_dispatches",
        "cost_total_usd", "cost_per_call_mean",
        "success_rate", "success_low_95", "success_high_95",
    ])
    for (agent, shape, model, _provider), b in sorted(buckets.items()):
        n = b["n"]
        if n == 0:
            continue
        if b["n_obs"] > 0:
            sr = b["n_success"] / b["n_obs"]
            lo, hi = beta_credible_interval(b["n_success"], b["n_obs"] - b["n_success"])
        else:
            sr, lo, hi = math.nan, math.nan, math.nan
        w.writerow([
            agent, shape, model, b["provider"], n,
            f"{b['cost']:.4f}", f"{(b['cost'] / n):.6f}",
            f"{sr:.4f}", f"{lo:.4f}", f"{hi:.4f}",
        ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
