#!/usr/bin/env python3
"""
pull-telemetry.py — extract retriever paper-stream records into a paper-ready
raw stream at data/raw/queries.jsonl.

Reads the production retriever telemetry that backs the empirical claims in
§6 of the paper. The paper-stream is emitted by
`internal/bdmemory/paper_stream.go` (bd: blackrim-41nn) and contains
per-query records of: query hash (anonymised), query length, inferred query
class, per-scorer top-k scores and latency, final fused ranks, total
latency.

Usage:
    python scripts/pull-telemetry.py --since=30d --src ~/research/blackrim-retriever-paper/data/raw/queries.jsonl
    python scripts/pull-telemetry.py --since=all --out data/raw/queries.jsonl

This is the retriever-paper analogue of pull-telemetry.py in the
model-advisor paper. The retriever paper-stream is already query-hashed
(no plaintext queries), so unlike the model-advisor pipeline this script
mostly does time-window filtering and field projection rather than
pseudonymisation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _parse_since(s: str) -> datetime | None:
    if s in ("all", "0", ""):
        return None
    if s.endswith("d"):
        n = int(s[:-1])
        return datetime.now(timezone.utc) - timedelta(days=n)
    if s.endswith("h"):
        n = int(s[:-1])
        return datetime.now(timezone.utc) - timedelta(hours=n)
    raise ValueError(f"unrecognised --since value: {s}")


def _project(record: dict) -> dict | None:
    """Project a raw paper-stream record onto the fields the paper needs."""
    if "query_hash" not in record or "ts" not in record:
        return None
    return {
        "ts": record.get("ts"),
        "query_hash": record.get("query_hash"),
        "query_len": record.get("query_len"),
        "query_class": record.get("query_class"),
        "scorers": record.get("scorers", {}),
        "final_ranks": record.get("final_ranks", []),
        "latency_ms": record.get("latency_ms"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", default=os.environ.get(
        "BLACKRIM_RETRIEVER_PAPER_STREAM",
        os.path.expanduser(
            "~/research/blackrim-retriever-paper/data/raw/queries.jsonl"),
    ), help="Path to the paper-stream queries.jsonl.")
    p.add_argument("--since", default="30d",
                   help="Time window: 30d, 7d, 24h, all.")
    p.add_argument("--out", default="data/raw/queries.filtered.jsonl",
                   help="Output path for the filtered stream.")
    args = p.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"paper-stream source not found: {src}", file=sys.stderr)
        return 1

    cutoff = _parse_since(args.since)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    n_in, n_out = 0, 0
    with src.open() as f, out.open("w") as g:
        for line in f:
            n_in += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                ts = record.get("ts")
                if ts is None:
                    continue
                try:
                    when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if when < cutoff:
                    continue
            projected = _project(record)
            if projected is None:
                continue
            g.write(json.dumps(projected) + "\n")
            n_out += 1

    print(f"read {n_in} records; emitted {n_out} → {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
