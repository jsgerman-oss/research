#!/usr/bin/env python3
"""
aggregate-by-language.py — reduce compression-ratios JSONL to a per-language CSV.

Input: JSONL on stdin (output of pull-compression-ratios.py).
Output: CSV on stdout with one row per language.

CSV schema:
    lang,n_files,mean_ratio,mean_tokens_savings,floor_ratio,floor_pass

`floor_ratio` reflects the per-language compression floor enforced by
the in-tree benchmark assertion in
`cmd/gt/compress_structure_bench_test.go` and reported in ADR-0002:

    Go ≤ 0.50, Python ≤ 0.20, JS ≤ 0.50, TS ≤ 0.50

(ratio = output / input; lower is better). The asymmetry between the
floor and our paper's reported tokens-savings numbers is intentional:
the floor is permissive; the measured value clears it comfortably.

Consumed by §6.2 figures/compression-by-lang.tex via pgfplots.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict

# Per-language floors from ADR-0002 (ratio; lower is better).
FLOORS = {
    "go":         0.50,
    "python":     0.20,
    "javascript": 0.50,
    "typescript": 0.50,
}


def main() -> int:
    per_lang: dict[str, list[dict]] = defaultdict(list)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        per_lang[rec["lang"]].append(rec)

    w = csv.writer(sys.stdout)
    w.writerow(["lang", "n_files", "mean_ratio", "mean_tokens_savings",
                "floor_ratio", "floor_pass"])
    for lang, recs in sorted(per_lang.items()):
        n = len(recs)
        if n == 0:
            continue
        mean_ratio = statistics.mean(r["ratio"] for r in recs)
        mean_savings = statistics.mean(r["tokens_savings"] for r in recs)
        floor = FLOORS.get(lang, 1.0)
        w.writerow([
            lang,
            n,
            f"{mean_ratio:.4f}",
            f"{mean_savings:.4f}",
            f"{floor:.4f}",
            "pass" if mean_ratio <= floor else "fail",
        ])

    return 0


if __name__ == "__main__":
    sys.exit(main())
