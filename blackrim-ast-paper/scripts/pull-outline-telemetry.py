#!/usr/bin/env python3
"""
pull-outline-telemetry.py — aggregate outline-discipline events for §6.5.

Backs OQ-AST-3 (outline-discipline adoption trajectory). Once the hook
has been running for at least 14 days, this script:

  1. Reads .beads/telemetry/outline-events.jsonl from the *central
     Blackrim sink* (default: $BLACKRIM_HOME/.beads/telemetry/, where
     $BLACKRIM_HOME defaults to $HOME/Code/blackrim). The hook writes
     here for every qualifying Read across the factory + every factory
     project the user works in, tagged with `project_root` so we can
     federate the data without conflating projects.
  2. Buckets events by UTC day and project_root.
  3. Computes the rolling 7-day hit-rate: fraction of large-file Reads
     that had a prior outline-call in the same transcript.
  4. Emits CSV: day, project_root, n_reads_large_file,
     n_outline_called_prior, hit_rate, hit_rate_7d_rolling.

The §6.5 figure plots hit_rate_7d_rolling vs. day (overall and per
project_root), with the 0.80 promote-to-block threshold marked
horizontally.

Until telemetry accumulates the script emits the CSV header only,
keeping the LaTeX build green during draft revisions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_events(path: Path):
    if not path.exists():
        return
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("tool") != "Read":
                continue  # adoption metric is Read-only; Bash events log-only
            ts = rec.get("ts", "")
            if not ts:
                continue
            try:
                day = datetime.strptime(ts[:10], "%Y-%m-%d").date().isoformat()
            except ValueError:
                continue
            yield {
                "day": day,
                "project_root": rec.get("project_root", "unknown"),
                "outline_called_prior": bool(rec.get("outline_called_prior", False)),
            }


def aggregate(events):
    """Group by (day, project_root) → (n_reads, n_with_prior)."""
    buckets: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for ev in events:
        key = (ev["day"], ev["project_root"])
        buckets[key][0] += 1
        if ev["outline_called_prior"]:
            buckets[key][1] += 1
    return buckets


def rolling_hit_rate(per_day_rates: list[tuple[str, float, int]], window: int = 7):
    """Compute a rolling N-day mean over per-day rates weighted by sample count."""
    out = []
    for i in range(len(per_day_rates)):
        lo = max(0, i - window + 1)
        slice_ = per_day_rates[lo : i + 1]
        total_n = sum(n for _, _, n in slice_)
        if total_n == 0:
            out.append(None)
            continue
        rate = sum(r * n for _, r, n in slice_) / total_n
        out.append(rate)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    default_home = os.environ.get("BLACKRIM_HOME", str(Path.home() / "Code" / "blackrim"))
    default_path = Path(default_home) / ".beads" / "telemetry" / "outline-events.jsonl"
    p.add_argument(
        "--telemetry",
        default=str(default_path),
        help="Path to outline-events.jsonl (default: $BLACKRIM_HOME/.beads/telemetry/outline-events.jsonl)",
    )
    p.add_argument(
        "--project-filter",
        default=None,
        help="If set, only include events whose project_root contains this substring.",
    )
    args = p.parse_args()

    src = Path(args.telemetry)
    events = list(parse_events(src))
    if args.project_filter:
        events = [e for e in events if args.project_filter in e["project_root"]]

    w = csv.writer(sys.stdout)
    w.writerow([
        "day",
        "project_root",
        "n_reads_large_file",
        "n_outline_called_prior",
        "hit_rate",
        "hit_rate_7d_rolling",
    ])

    if not events:
        # No data yet — emit header only. The LaTeX build expects this file.
        return 0

    buckets = aggregate(events)
    # Compute per-project rolling rate. Days are sorted globally for the rolling
    # window to be stable across project_root groups.
    per_project: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
    for (day, root), (n_reads, n_prior) in sorted(buckets.items()):
        rate = n_prior / n_reads if n_reads else 0.0
        per_project[root].append((day, rate, n_reads))

    for root, daily in sorted(per_project.items()):
        rolling = rolling_hit_rate(daily, window=7)
        for (day, rate, n_reads), r7 in zip(daily, rolling):
            n_prior_day = round(rate * n_reads)
            w.writerow([
                day,
                root,
                n_reads,
                n_prior_day,
                f"{rate:.4f}",
                f"{r7:.4f}" if r7 is not None else "",
            ])

    return 0


if __name__ == "__main__":
    sys.exit(main())
