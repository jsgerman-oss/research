#!/usr/bin/env python3
"""
bench-converged.py — run pull-compression-ratios.py N_ITER times across
N_WORKERS threads (default 7×7) and emit a converged CSV with per-file
mean/stdev across iterations.

The underlying bench (`pull-compression-ratios.py` in corpus mode) is
regex over text — fully deterministic — so the expected stdev is exactly
zero on a stable filesystem. This script's purpose is reproducibility
verification, not denoising: a non-zero stdev would surface a real bug
(e.g., file-system race, hidden non-determinism in the regex compile
path, etc.).

There is no GPU surface — the work is small enough that even multi-
threading mostly amortises subprocess-spawn overhead rather than
compute. Reported wall-clock + per-iteration counts let a reader see
both convergence and runtime.

Usage:
    python scripts/bench-converged.py
    python scripts/bench-converged.py --workers 7 --iterations 7
    python scripts/bench-converged.py --workers 1 --iterations 1   # debug
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_BENCH = _SCRIPT_DIR / "pull-compression-ratios.py"
_PAPER_ROOT = _SCRIPT_DIR.parent
_RAW_DIR = _PAPER_ROOT / "data" / "raw"
_AGG_DIR = _PAPER_ROOT / "data" / "aggregated"

_METRIC_FIELDS = (
    "loc",
    "raw_bytes",
    "outline_bytes",
    "ratio",
    "tokens_raw_est",
    "tokens_outline_est",
    "tokens_savings",
)


def _run_one_iteration(iter_idx: int) -> tuple[int, list[dict], float]:
    """Run the bench once and return (iter, records, wall_seconds)."""
    t0 = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(_BENCH)],
        capture_output=True,
        text=True,
        check=True,
    )
    wall = time.monotonic() - t0
    records: list[dict] = []
    for ln in result.stdout.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        records.append(json.loads(ln))
    return iter_idx, records, wall


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=7, help="Thread-pool size (default 7).")
    parser.add_argument("--iterations", type=int, default=7, help="Iterations to run (default 7).")
    parser.add_argument(
        "--out",
        default=str(_AGG_DIR / "compression-ratios-converged.csv"),
        help="Output converged CSV (default: data/aggregated/compression-ratios-converged.csv).",
    )
    args = parser.parse_args()

    _AGG_DIR.mkdir(parents=True, exist_ok=True)
    _RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"running {args.iterations} iteration(s) across {args.workers} worker(s) "
        f"→ bench={_BENCH.name}",
        file=sys.stderr,
    )
    iter_records: dict[int, list[dict]] = {}
    iter_walls: dict[int, float] = {}
    t_all_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(_run_one_iteration, i + 1) for i in range(args.iterations)]
        for fut in as_completed(futures):
            i, recs, wall = fut.result()
            iter_records[i] = recs
            iter_walls[i] = wall
            print(f"  iter {i:2d}: {len(recs):3d} records  wall={wall:6.2f}s", file=sys.stderr)
    t_all = time.monotonic() - t_all_start

    # Persist raw per-iteration JSONL for full audit trail.
    for i, recs in iter_records.items():
        raw = _RAW_DIR / f"compression-ratios-iter-{i}.jsonl"
        with open(raw, "w") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    # Aggregate: keys = (lang, file); collect per-metric value lists.
    by_key: dict[tuple[str, str], dict[str, list[float]]] = {}
    for recs in iter_records.values():
        for r in recs:
            key = (r["lang"], r["file"])
            if key not in by_key:
                by_key[key] = {m: [] for m in _METRIC_FIELDS}
            for m in _METRIC_FIELDS:
                by_key[key][m].append(float(r[m]))

    # Write converged CSV with mean + stdev for each metric.
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = ["lang", "file", "n_iter"]
    for m in _METRIC_FIELDS:
        header.append(f"{m}_mean")
        header.append(f"{m}_stdev")
    with open(out_path, "w") as fh:
        fh.write(",".join(header) + "\n")
        for (lang, file), metrics in sorted(by_key.items()):
            row = [lang, file, str(len(next(iter(metrics.values()))))]
            for m in _METRIC_FIELDS:
                vals = metrics[m]
                mean = statistics.fmean(vals)
                stdev = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                row.append(f"{mean:.6f}")
                row.append(f"{stdev:.6f}")
            fh.write(",".join(row) + "\n")

    # Determinism summary
    nonzero_stdev_metrics = 0
    for metrics in by_key.values():
        for m in _METRIC_FIELDS:
            vals = metrics[m]
            if len(vals) > 1 and statistics.pstdev(vals) > 0:
                nonzero_stdev_metrics += 1

    print(f"\nconverged CSV: {out_path}", file=sys.stderr)
    print(f"  files               : {len(by_key)}", file=sys.stderr)
    print(f"  iterations per file : {args.iterations}", file=sys.stderr)
    print(f"  workers             : {args.workers}", file=sys.stderr)
    print(f"  total wall          : {t_all:.2f}s", file=sys.stderr)
    print(f"  metric-cells with stdev > 0: {nonzero_stdev_metrics}", file=sys.stderr)
    if nonzero_stdev_metrics == 0:
        print("  → bench is fully deterministic (expected).", file=sys.stderr)
    else:
        print("  → WARNING: non-determinism detected. Investigate.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
