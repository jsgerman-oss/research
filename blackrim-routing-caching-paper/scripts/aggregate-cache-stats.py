#!/usr/bin/env python3
"""Aggregate per-spawn cache statistics into a single CSV row backing
§7's calibration baseline.

Stdin: JSON-lines from pull-telemetry.py.
Stdout: single-row CSV with cache_creation_total, cache_read_total,
        read_to_creation_ratio, cache_hit_rate_estimate, sample_count.

Usage:
    python scripts/aggregate-cache-stats.py < data/raw/session-telemetry.json \\
        > data/aggregated/cache-stats.csv

Or invoke directly against the telemetry file:

    python scripts/aggregate-cache-stats.py \\
        --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl \\
        > data/aggregated/cache-stats.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys


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
    cache_enabled_count = 0

    for line in iter_rows():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        creation = int(row.get("cache_creation_input_tokens") or 0)
        read = int(row.get("cache_read_input_tokens") or 0)
        creation_total += creation
        read_total += read
        sample_count += 1
        if creation > 0 or read > 0:
            cache_enabled_count += 1

    ratio = (read_total / creation_total) if creation_total > 0 else 0.0
    # Hit rate: of cache-enabled spawns, what fraction read more than they
    # created? Imperfect heuristic but matches the deep-dive doc's framing.
    hit_rate = (
        cache_enabled_count / sample_count if sample_count > 0 else 0.0
    )

    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "metric",
            "value",
        ]
    )
    writer.writerow(["cache_creation_total_tokens", creation_total])
    writer.writerow(["cache_read_total_tokens", read_total])
    writer.writerow(["read_to_creation_ratio", f"{ratio:.2f}"])
    writer.writerow(["cache_enabled_spawn_rate", f"{hit_rate:.3f}"])
    writer.writerow(["sample_count", sample_count])
    writer.writerow(["cache_enabled_count", cache_enabled_count])


if __name__ == "__main__":
    main()
