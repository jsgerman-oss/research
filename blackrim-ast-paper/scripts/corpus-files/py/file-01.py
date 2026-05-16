#!/usr/bin/env python3
"""
pull-telemetry.py — extract dispatch records from .beads/telemetry/invocations.jsonl
into a paper-ready raw stream at data/raw/telemetry.jsonl.

Reads the production telemetry that backs the empirical claims in §6 of the
paper. Anonymises agent IDs and pseudonymises shape names by hashing.

Usage:
    python scripts/pull-telemetry.py --since=30d --repo /Users/jayse/Code/blackrim
    python scripts/pull-telemetry.py --since=all --out data/raw/telemetry.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
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


def _pseudonymise(value: str, salt: str = "blackrim-paper-2026") -> str:
    digest = hashlib.sha256((salt + value).encode()).hexdigest()
    return digest[:12]


def _normalise(record: dict) -> dict | None:
    """Project a raw telemetry record onto the fields the paper needs."""
    src = record.get("source", "")
    if src in ("dispatch", "dispatch_estimated", "subagent_stop_unbounded",
               "gt-cache-warm", "estimated"):
        return None
    return {
        "ts": record.get("ts"),
        "agent": _pseudonymise(record.get("agent", "unknown")),
        "shape": _pseudonymise(record.get("shape", "default")),
        "model": record.get("model"),
        "provider": record.get("provider", "anthropic"),
        "input_tokens": record.get("input_tokens"),
        "output_tokens": record.get("output_tokens"),
        "cache_creation_5m": record.get("cache_creation_5m_tokens"),
        "cache_creation_1h": record.get("cache_creation_1h_tokens"),
        "cache_read": record.get("cache_read_tokens"),
        "source": src,
        "session_id": _pseudonymise(record.get("session_id", "")),
        "outcome": record.get("outcome"),  # success|failure|unknown
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=os.environ.get("BLACKRIM_REPO",
                   "/Users/jayse/Code/blackrim"),
                   help="Path to the Blackrim repo root.")
    p.add_argument("--since", default="30d",
                   help="Time window: 30d, 7d, 24h, all.")
    p.add_argument("--out", default="data/raw/telemetry.jsonl",
                   help="Output path for the anonymised stream.")
    args = p.parse_args()

    src = Path(args.repo) / ".beads" / "telemetry" / "invocations.jsonl"
    if not src.exists():
        print(f"telemetry source not found: {src}", file=sys.stderr)
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
            normalised = _normalise(record)
            if normalised is None:
                continue
            g.write(json.dumps(normalised) + "\n")
            n_out += 1

    print(f"read {n_in} records; emitted {n_out} → {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
