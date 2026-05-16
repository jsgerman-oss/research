#!/usr/bin/env python3
"""Aggregate per-spawn cache statistics into a single CSV row backing
§7's calibration baseline.

Stdin: JSON-lines from pull-telemetry.py.
Stdout: CSV with cache_creation_total, cache_read_total,
        read_to_creation_ratio, cache_enabled_spawn_rate,
        cache_enabled_real_spawn_rate, savings_vs_no_caching,
        sample_count, real_spawn_count, cache_enabled_count.

Usage:
    python scripts/aggregate-cache-stats.py < data/raw/session-telemetry.json \\
        > data/aggregated/cache-stats.csv

Or invoke directly against the telemetry file:

    python scripts/aggregate-cache-stats.py \\
        --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl \\
        > data/aggregated/cache-stats.csv

Savings derivation (from docs/research/cache-control-deep-dive.md):
    cost_with_cache = inp_tokens * price + cc_tokens * price * 1.25
                      + cr_tokens * price * 0.10
    cost_without_cache = (inp_tokens + cc_tokens + cr_tokens) * price
    savings = 1 - (cost_with_cache / cost_without_cache)

Model pricing (Anthropic public rate sheet, 2026-04-24, USD/MTok base):
    claude-haiku-*: 1.00
    claude-sonnet-*: 3.00
    claude-opus-*: 5.00
    unknown: 2.40 (weighted avg: 40% haiku, 50% sonnet, 10% opus)

Real-spawn vs all-spawn distinction:
    Records with source in {subagent_stop, gt-cache-warm, dispatch} carry
    real API token counts. Records with source in {dispatch_estimated,
    subagent_stop_estimated} are synthetic stubs with zero cache fields
    and must not be included in the denominator of cache_enabled_spawn_rate.
    cache_enabled_spawn_rate uses ALL records (including estimated) for the
    denominator -- this matches the aggregate script's original definition.
    cache_enabled_real_spawn_rate uses only real-source records.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys

# Sources that carry real API token counts (not estimated/stubbed)
REAL_SOURCES = frozenset({"subagent_stop", "gt-cache-warm", "dispatch"})

# Model base pricing in USD/MTok
MODEL_PRICE = {
    "claude-haiku-4-5-20251001": 1.0,
    "claude-haiku-4-5": 1.0,
    "claude-sonnet-4-6": 3.0,
    "claude-opus-4-7": 5.0,
}
PRICE_UNKNOWN = 2.40  # weighted avg (40% haiku, 50% sonnet, 10% opus)


def model_price(model: str) -> float:
    if not model or model == "unknown":
        return PRICE_UNKNOWN
    for prefix, price in MODEL_PRICE.items():
        if model.startswith(prefix.split("-20")[0]):
            return price
    return PRICE_UNKNOWN


def iter_rows():
    ap = argparse.ArgumentParser()
    ap.add_argument("--telemetry", default="-")
    args = ap.parse_args()
    if args.telemetry == "-":
        return iter(sys.stdin)
    return open(args.telemetry)


def main() -> None:
    creation_total = 0
    read_total = 0
    sample_count = 0
    real_spawn_count = 0
    cache_enabled_count = 0
    cost_with_cache = 0.0
    cost_without_cache = 0.0

    for line in iter_rows():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        source = row.get("source", "")
        is_real = source in REAL_SOURCES

        creation = int(row.get("cache_creation_input_tokens") or 0)
        read = int(row.get("cache_read_input_tokens") or 0)
        inp = int(row.get("input_tokens") or 0)

        creation_total += creation
        read_total += read
        sample_count += 1

        if is_real:
            real_spawn_count += 1
            price = model_price(row.get("model", "unknown"))
            cost_with_cache += (
                inp * price
                + creation * price * 1.25
                + read * price * 0.10
            ) / 1_000_000
            cost_without_cache += (inp + creation + read) * price / 1_000_000

        if creation > 0 or read > 0:
            cache_enabled_count += 1

    ratio = (read_total / creation_total) if creation_total > 0 else 0.0

    # cache_enabled_spawn_rate: fraction of ALL sampled spawns that carried
    # any cache tokens (matches the original definition; low because estimated
    # stubs are included in denominator).
    hit_rate_all = (
        cache_enabled_count / sample_count if sample_count > 0 else 0.0
    )

    # cache_enabled_real_spawn_rate: fraction of REAL-source spawns that
    # carried any cache tokens (the operationally meaningful rate).
    real_cache_count = min(cache_enabled_count, real_spawn_count)
    hit_rate_real = (
        real_cache_count / real_spawn_count if real_spawn_count > 0 else 0.0
    )

    # savings_vs_no_caching: cost reduction from prefix caching over
    # the real-spawn subset (see module docstring for derivation).
    savings = (
        1.0 - cost_with_cache / cost_without_cache
        if cost_without_cache > 0
        else 0.0
    )

    writer = csv.writer(sys.stdout)
    writer.writerow(["metric", "value"])
    writer.writerow(["cache_creation_total_tokens", creation_total])
    writer.writerow(["cache_read_total_tokens", read_total])
    writer.writerow(["read_to_creation_ratio", f"{ratio:.2f}"])
    writer.writerow(["cache_enabled_spawn_rate", f"{hit_rate_all:.3f}"])
    writer.writerow(["cache_enabled_real_spawn_rate", f"{hit_rate_real:.3f}"])
    writer.writerow(["savings_vs_no_caching", f"{savings:.3f}"])
    writer.writerow(["sample_count", sample_count])
    writer.writerow(["real_spawn_count", real_spawn_count])
    writer.writerow(["cache_enabled_count", cache_enabled_count])


if __name__ == "__main__":
    main()
