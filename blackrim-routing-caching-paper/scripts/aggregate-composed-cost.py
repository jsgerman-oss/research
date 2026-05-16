#!/usr/bin/env python3
"""
Aggregate composed cost reduction from prefix-cache and plan-cache measurements.

Reads:
  data/aggregated/cache-stats.csv      — prefix-cache baseline (from RC-01)
  data/aggregated/plancache-summary-real.csv  — plan-cache hit rate (real telemetry, RC-06)
  data/aggregated/plancache-summary.csv       — plan-cache hit rate (fixture/synthetic, RC-05)

Outputs:
  data/aggregated/composed-cost.csv    — single-row CSV with composed savings

Math
----
Let P = prefix_savings_baseline (from cache-stats.csv; fraction of cost saved by prefix cache)
Let H = true_hit_rate (from plancache-summary; fraction of requests where plan cache fires
        a correct hit — i.e., signature matches AND task types agree)

Prefix cache alone eliminates fraction P of total cost.
Remaining cost after prefix cache = (1 - P).

Plan cache applies to the H fraction of requests where it fires correctly.
On those requests, the plan is retrieved from cache rather than re-generated,
saving the full remaining cost fraction for that request.

Marginal plan-cache savings (as fraction of total original cost):
    marginal_plancache = H * (1 - P)

Composed savings:
    composed = P + H * (1 - P)

This formula treats prefix-cache savings and plan-cache savings as
multiplicative on the residual cost, not additive — which is the conservative
and correct interpretation: plan-cache only applies to the cost that prefix
caching did not already cover.

Reference: §7 "Plan-cache evaluation" in the routing-caching paper.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path


def read_csv_row(path: Path) -> dict[str, str]:
    """Read the first data row of a CSV as a dict."""
    with path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            return dict(row)
    raise ValueError(f"No data rows in {path}")


def main() -> None:
    # Resolve paths relative to this script's location (scripts/)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    data_dir = repo_root / "data" / "aggregated"

    cache_stats_path = data_dir / "cache-stats.csv"
    plancache_real_path = data_dir / "plancache-summary-real.csv"
    plancache_fixture_path = data_dir / "plancache-summary.csv"
    out_path = data_dir / "composed-cost.csv"

    # --- Load prefix-cache baseline ---
    if not cache_stats_path.exists():
        sys.exit(f"ERROR: cache-stats.csv not found at {cache_stats_path}")
    cache_row = read_csv_row(cache_stats_path)
    # cache-stats.csv uses 'metric,value' layout; find the savings row
    # Actually cache-stats.csv has named columns: metric,value per row.
    # Re-read as key-value pairs.
    prefix_savings: float | None = None
    with cache_stats_path.open() as fh:
        reader = csv.reader(fh)
        next(reader)  # skip header
        for metric, value in reader:
            if metric.strip() == "savings_vs_no_caching":
                prefix_savings = float(value)
                break
    if prefix_savings is None:
        sys.exit("ERROR: 'savings_vs_no_caching' not found in cache-stats.csv")

    # --- Load plan-cache results ---
    # Prefer real telemetry; fall back to fixture if real not present.
    if plancache_real_path.exists():
        plancache_row = read_csv_row(plancache_real_path)
        plancache_source = "real telemetry"
        plancache_path_used = plancache_real_path
    elif plancache_fixture_path.exists():
        plancache_row = read_csv_row(plancache_fixture_path)
        plancache_source = "synthetic fixture"
        plancache_path_used = plancache_fixture_path
    else:
        sys.exit("ERROR: neither plancache-summary-real.csv nor plancache-summary.csv found")

    n_dispatches = int(plancache_row["n_dispatches"])
    true_hit_rate = float(plancache_row["true_hit_rate"])
    false_hit_rate = float(plancache_row["false_hit_rate"])
    hit_rate = float(plancache_row["hit_rate"])

    # --- Compute composed cost reduction ---
    P = prefix_savings
    H = true_hit_rate
    marginal_plancache = H * (1.0 - P)
    composed = P + marginal_plancache

    prefix_only_savings_pct = round(P * 100, 2)
    plancache_only_savings_pct = round(H * 100, 2)
    marginal_plancache_pct = round(marginal_plancache * 100, 2)
    composed_savings_pct = round(composed * 100, 2)

    # --- Write output ---
    fieldnames = [
        "prefix_only_savings_pct",
        "plancache_only_savings_pct",
        "marginal_plancache_pct",
        "composed_savings_pct",
        "true_hit_rate",
        "false_hit_rate",
        "hit_rate",
        "n_dispatches",
        "plancache_source",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "prefix_only_savings_pct": prefix_only_savings_pct,
            "plancache_only_savings_pct": plancache_only_savings_pct,
            "marginal_plancache_pct": marginal_plancache_pct,
            "composed_savings_pct": composed_savings_pct,
            "true_hit_rate": true_hit_rate,
            "false_hit_rate": false_hit_rate,
            "hit_rate": hit_rate,
            "n_dispatches": n_dispatches,
            "plancache_source": plancache_source,
        })

    print(f"Composed cost reduction summary")
    print(f"  Source: {plancache_path_used}  (n={n_dispatches}, {plancache_source})")
    print(f"  Prefix-cache savings (baseline)  : {prefix_only_savings_pct:.1f}%")
    print(f"  Plan-cache hit rate (true hits)  : {plancache_only_savings_pct:.1f}%")
    print(f"  Marginal plan-cache savings      : {marginal_plancache_pct:.2f}%")
    print(f"  Composed savings (prefix+plan)   : {composed_savings_pct:.1f}%")
    print(f"  Written: {out_path}")


if __name__ == "__main__":
    main()
