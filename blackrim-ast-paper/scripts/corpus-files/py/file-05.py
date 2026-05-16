#!/usr/bin/env python3
"""
aggregate-by-class.py — roll up data/raw/queries.jsonl into per-(query-class,
arm) summary statistics for §6 of the paper.

Reads stdin (one paper-stream JSONL record per line as emitted by
pull-telemetry.py) and writes a CSV to stdout.

Output schema:
    query_class, arm, n_queries, latency_ms_p50, latency_ms_p95,
    ndcg10_mean, ndcg10_low_95, ndcg10_high_95
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from typing import Tuple


def _percentile(xs: list, p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _arm_for(scorers: dict) -> str:
    """Derive the fusion-config arm label from the scorer set used."""
    methods = sorted(s.get("method", k) for k, s in scorers.items())
    if not methods:
        return "none"
    return "+".join(methods)


def main() -> int:
    buckets: dict[Tuple[str, str], dict] = defaultdict(
        lambda: {"n": 0, "lat": [], "ndcg": []}
    )

    for line in sys.stdin:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        qclass = r.get("query_class", "unknown")
        arm = _arm_for(r.get("scorers", {}))
        b = buckets[(qclass, arm)]
        b["n"] += 1
        if r.get("latency_ms") is not None:
            b["lat"].append(float(r["latency_ms"]))
        # NDCG@10 lands here from the labeled-eval pipeline; the paper-stream
        # only carries per-scorer scores at this stage.
        if r.get("ndcg10") is not None:
            b["ndcg"].append(float(r["ndcg10"]))

    w = csv.writer(sys.stdout)
    w.writerow([
        "query_class", "arm", "n_queries",
        "latency_ms_p50", "latency_ms_p95",
        "ndcg10_mean", "ndcg10_low_95", "ndcg10_high_95",
    ])
    for (qclass, arm), b in sorted(buckets.items()):
        n = b["n"]
        if n == 0:
            continue
        p50 = _percentile(b["lat"], 0.50) if b["lat"] else float("nan")
        p95 = _percentile(b["lat"], 0.95) if b["lat"] else float("nan")
        if b["ndcg"]:
            mean = sum(b["ndcg"]) / len(b["ndcg"])
            # naive symmetric CI placeholder; paired bootstrap belongs in
            # the eval-suite script.
            sd = math.sqrt(
                sum((x - mean) ** 2 for x in b["ndcg"]) / max(1, len(b["ndcg"]) - 1)
            )
            lo = max(0.0, mean - 1.96 * sd / math.sqrt(len(b["ndcg"])))
            hi = min(1.0, mean + 1.96 * sd / math.sqrt(len(b["ndcg"])))
        else:
            mean, lo, hi = float("nan"), float("nan"), float("nan")
        w.writerow([
            qclass, arm, n,
            f"{p50:.4f}", f"{p95:.4f}",
            f"{mean:.4f}", f"{lo:.4f}", f"{hi:.4f}",
        ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
