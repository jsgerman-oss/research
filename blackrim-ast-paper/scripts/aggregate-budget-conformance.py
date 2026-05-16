#!/usr/bin/env python3
"""
aggregate-budget-conformance.py — aggregate JSONL from budget-corpus-walk.py.

Reads JSONL from stdin, groups by repo, and emits a CSV with:
    repo, n_files, mean_outline_tokens, p50, p95, p99, within_budget_pct

Uses statistics.quantiles (Python ≥3.8).
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict


FIELDNAMES = [
    "repo",
    "n_files",
    "mean_outline_tokens",
    "p50",
    "p95",
    "p99",
    "within_budget_pct",
]


def quantile(data: list[float], q: float) -> float:
    """Return the q-th quantile (0 < q < 1) via linear interpolation."""
    n = len(data)
    if n == 0:
        return float("nan")
    if n == 1:
        return data[0]
    sorted_data = sorted(data)
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_data[lo]
    frac = pos - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac


def main() -> int:
    # repo_name → list of token estimates
    repo_tokens: dict[str, list[float]] = defaultdict(list)
    # repo_name → count of within-budget files
    repo_within: dict[str, int] = defaultdict(int)

    line_num = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        line_num += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"[warn] skipping malformed line {line_num}: {exc}", file=sys.stderr)
            continue

        repo = rec.get("repo", "unknown")
        tokens = rec.get("outline_tokens_est")
        within = rec.get("within_budget", False)

        if tokens is None:
            print(f"[warn] missing outline_tokens_est on line {line_num}", file=sys.stderr)
            continue

        repo_tokens[repo].append(float(tokens))
        if within:
            repo_within[repo] += 1

    if not repo_tokens:
        print("[error] no records read from stdin", file=sys.stderr)
        return 2

    writer = csv.DictWriter(sys.stdout, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()

    for repo in sorted(repo_tokens.keys()):
        tokens = repo_tokens[repo]
        n = len(tokens)
        within_count = repo_within[repo]
        mean = statistics.mean(tokens) if n else float("nan")
        p50 = quantile(tokens, 0.50)
        p95 = quantile(tokens, 0.95)
        p99 = quantile(tokens, 0.99)
        within_pct = 100.0 * within_count / n if n else 0.0

        writer.writerow({
            "repo": repo,
            "n_files": n,
            "mean_outline_tokens": round(mean, 1),
            "p50": round(p50, 1),
            "p95": round(p95, 1),
            "p99": round(p99, 1),
            "within_budget_pct": round(within_pct, 1),
        })

    return 0


if __name__ == "__main__":
    sys.exit(main())
