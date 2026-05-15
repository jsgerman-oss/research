#!/usr/bin/env python3
"""
measure-outline-latency.py — STUB. Backs §6.4 (OQ-AST-2).

Once OQ-AST-2 is unblocked, this script will:

  1. Sample the polyglot corpus pinned in scripts/corpus.txt and bucket
     files by LoC range: [200,500), [500,1000), [1000,2000),
     [2000,5000), [5000+].
  2. For each file, call `gt outline <file>` 10 times and record the
     wall-clock distribution (min, p50, p95, max). The first call per
     file is treated as a cold start and reported separately.
  3. Emit CSV: lang, loc_bucket, n_files, cold_p50, cold_p95,
     warm_p50, warm_p95.

The §6.4 figure plots warm_p50 and warm_p95 vs. loc_bucket per
language. The target is warm_p95 < 500ms on every bucket.

Emitting a header-only CSV now keeps the LaTeX build from breaking
during draft revisions; replace with the real implementation when the
corpus and timing harness land.
"""
from __future__ import annotations

import csv
import sys


def main() -> int:
    w = csv.writer(sys.stdout)
    w.writerow(["lang", "loc_bucket", "n_files",
                "cold_p50_ms", "cold_p95_ms",
                "warm_p50_ms", "warm_p95_ms"])
    # No rows yet — OQ-AST-2 dataset is pending.
    return 0


if __name__ == "__main__":
    sys.exit(main())
