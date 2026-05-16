#!/usr/bin/env python3
"""Aggregate session telemetry into trim-results.csv.

Stdin: JSON-lines from pull-telemetry.py (one record per commit).
Stdout: CSV (sha, date, claude_md_lines, claude_md_chars,
        delta_lines_vs_baseline, delta_pct_lines, delta_chars_vs_baseline,
        delta_pct_chars, subject).

Usage:
    python scripts/aggregate-trim-results.py < data/raw/session-telemetry.json \\
        > data/aggregated/trim-results.csv
"""

from __future__ import annotations

import csv
import json
import sys


def main() -> None:
    records = [json.loads(line) for line in sys.stdin if line.strip()]
    if not records:
        print("no input records", file=sys.stderr)
        sys.exit(1)

    baseline_lines = records[0]["claude_md"]["lines"]
    baseline_chars = records[0]["claude_md"]["chars"]

    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "sha",
            "date",
            "claude_md_lines",
            "claude_md_chars",
            "delta_lines_vs_baseline",
            "delta_pct_lines",
            "delta_chars_vs_baseline",
            "delta_pct_chars",
            "subject",
        ]
    )

    for r in records:
        l = r["claude_md"]["lines"]
        c = r["claude_md"]["chars"]
        dl = l - baseline_lines
        dc = c - baseline_chars
        pct_l = (dl / baseline_lines * 100.0) if baseline_lines else 0.0
        pct_c = (dc / baseline_chars * 100.0) if baseline_chars else 0.0
        writer.writerow(
            [
                r["sha"][:7],
                r["author_iso"][:10],
                l,
                c,
                dl,
                f"{pct_l:.1f}",
                dc,
                f"{pct_c:.1f}",
                r["subject"],
            ]
        )


if __name__ == "__main__":
    main()
