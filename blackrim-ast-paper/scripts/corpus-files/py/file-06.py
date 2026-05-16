#!/usr/bin/env python3
"""
run-eval-suite.py — evaluate a candidate retrieval policy against held-out
labeled relevance data.

Reads:
    data/raw/queries.jsonl       (paper-stream production queries)
    data/raw/relevance.jsonl     (held-out per-query relevance judgements)
Writes:
    data/aggregated/<policy>-results.csv

Policies implemented (stubs — full impls land alongside the paper draft):
    keyword           — legacy bd-memory scorer (Blackrim historical default)
    bm25              — canonical sparse baseline; per-class safety floor
    bm25-decay        — BM25 + 30-day exponential decay; Q4 safety floor
    hybrid-rrf        — BM25 + SPLADE + dense fused via Cormack 2009 RRF k=60
    hybrid-cc         — BM25 + dense fused via convex combination, alpha tuned
                        per query class (Bruch et al. 2023)
    conservative-cb   — CCBandit-Retriever policy (Algorithm 1 of the paper)

Per-class baseline mapping (used by conservative-cb):
    Q1 technical-lookup       baseline = bm25
    Q2 failure-recall         baseline = keyword + failure-tag boost
    Q3 agent-scoped           baseline = bm25
    Q4 continuity             baseline = bm25-decay
    Q5 concept-bridge         baseline = bm25
    Q6 exact-id-or-slug       baseline = bm25

The conservative-bandit budget per class controls exploration headroom;
Critical classes (Q2, Q6) get budget=0 (hard no-regression).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path


_POLICIES = (
    "keyword", "bm25", "bm25-decay",
    "hybrid-rrf", "hybrid-cc", "conservative-cb",
)


def _select(policy: str, signals: dict, *, posteriors: dict,
            rng: random.Random) -> str:
    """Return the arm chosen by `policy` for the given query signals.

    Stubs only — full implementations land in the paper-draft pass.
    """
    if policy == "keyword":
        return "keyword"
    if policy == "bm25":
        return "bm25"
    if policy == "bm25-decay":
        return "bm25+decay"
    if policy == "hybrid-rrf":
        return "bm25+splade+dense+rrf"
    if policy == "hybrid-cc":
        return "bm25+dense+cc"
    if policy == "conservative-cb":
        # TODO: wire in the per-(class, arm) posteriors and conservative-budget
        # tracker per Algorithm 1 of the paper. Stub returns the per-class
        # baseline today.
        baseline = {
            "technical-lookup": "bm25",
            "failure-recall":   "keyword+failtag",
            "agent-scoped":     "bm25",
            "continuity":       "bm25+decay",
            "concept-bridge":   "bm25",
            "exact-id":         "bm25",
        }
        return baseline.get(signals.get("query_class", ""), "bm25")
    raise ValueError(f"unknown policy: {policy}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--policy", required=True, choices=_POLICIES)
    p.add_argument("--queries", default="data/raw/queries.jsonl")
    p.add_argument("--relevance", default="data/raw/relevance.jsonl",
                   help="Held-out per-query relevance judgements (TODO).")
    p.add_argument("--out", default="data/aggregated/{policy}-results.csv")
    p.add_argument("--seed", type=int, default=20260509)
    args = p.parse_args()

    rng = random.Random(args.seed)
    posteriors: dict = defaultdict(lambda: (0, 0))

    out_path = args.out.format(policy=args.policy)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    with open(args.queries) as src, open(out_path, "w", newline="") as dst:
        w = csv.writer(dst)
        w.writerow(["ts", "query_hash", "query_class", "policy",
                    "arm_picked", "ndcg10_estimated"])
        for line in src:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            signals = {
                "query_hash":  r.get("query_hash"),
                "query_class": r.get("query_class", "unknown"),
                "query_len":   r.get("query_len"),
            }
            arm = _select(args.policy, signals, posteriors=posteriors, rng=rng)
            ndcg = _est_ndcg(arm, signals)
            w.writerow([r.get("ts"), signals["query_hash"],
                        signals["query_class"], args.policy, arm,
                        f"{ndcg:.4f}"])

    print(f"wrote {out_path}", file=sys.stderr)
    return 0


def _est_ndcg(arm: str, signals: dict) -> float:
    """Rough off-policy NDCG@10 estimate per arm + class.

    Real evaluation requires labeled relevance judgements
    (data/raw/relevance.jsonl, TODO). This stub returns nan so downstream
    aggregation can recognise un-evaluated rows.
    """
    return float("nan")


if __name__ == "__main__":
    raise SystemExit(main())
