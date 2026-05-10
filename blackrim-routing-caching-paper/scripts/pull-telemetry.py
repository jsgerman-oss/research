#!/usr/bin/env python3
"""Pull session telemetry for the routing+caching paper §7.

Reads from the Blackrim repo's .beads/telemetry/invocations.jsonl,
extracts cache_creation_input_tokens vs cache_read_input_tokens per
spawn, and emits a single JSON record per invocation. Stdout is
JSON-lines.

Usage:
    python scripts/pull-telemetry.py --since 2026-05-01 \\
        --repo /Users/jayse/Code/blackrim \\
        > data/raw/session-telemetry.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-05-01")
    ap.add_argument(
        "--repo", default="/Users/jayse/Code/blackrim", type=Path
    )
    args = ap.parse_args()

    since_ts = datetime.fromisoformat(args.since)
    telemetry_path = args.repo / ".beads/telemetry/invocations.jsonl"
    if not telemetry_path.exists():
        print(f"telemetry not found: {telemetry_path}", file=sys.stderr)
        sys.exit(2)

    kept = 0
    skipped = 0
    with open(telemetry_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            ts_str = row.get("ts") or row.get("timestamp") or ""
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.replace(tzinfo=None) < since_ts:
                    continue
            except (ValueError, AttributeError):
                # No parseable timestamp; keep but flag
                pass

            # Extract cache fields
            out = {
                "ts": row.get("ts"),
                "agent": row.get("agent"),
                "model": row.get("model"),
                "session": row.get("session"),
                "input_tokens": int(row.get("input_tokens") or 0),
                "output_tokens": int(row.get("output_tokens") or 0),
                "cache_creation_input_tokens": int(
                    row.get("cache_creation_input_tokens") or 0
                ),
                "cache_read_input_tokens": int(
                    row.get("cache_read_input_tokens") or 0
                ),
                "duration_ms": int(row.get("duration_ms") or 0),
                "source": row.get("source"),
            }
            print(json.dumps(out))
            kept += 1

    print(
        f"# kept {kept}, skipped {skipped} (unparseable)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
