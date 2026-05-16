#!/usr/bin/env python3
"""
Plan-cache index builder for the Blackrim routing-caching paper.

Reads historical Blackrim dispatches (JSONL), extracts a plan signature for
each, embeds the user query with all-MiniLM-L6-v2, and writes a JSONL index
file.  No live API calls — all similarity is computed locally.

Plan signature
--------------
A plan signature is an ordered, coarse-grained string encoding the sequence
of tool calls an agent emitted before completing its task.  Each element is:

    <tool>:<coarse-target>

where the coarse target is derived from the raw argument by:
  - Keeping only the top-level directory component for file paths
    (``internal/cache/manager.go`` → ``internal/``)
  - Preserving shell command verbs for ``Bash`` calls (first token only)
  - Lowercasing and stripping punctuation

Elements are joined with a pipe ``|``.  Example:

    Read:internal/|Bash:go|Edit:internal/

This abstraction level was chosen to balance hit rate vs false-hit rate:
- Too fine (full paths): near-zero hits — every request looks unique
- Too coarse (tool name only): high false-hit rate — unrelated plans match

See README.md for the design rationale and trade-off discussion.

Usage
-----
    # Build index from fixture data (--dry-run: no embedding model loaded):
    python scripts/eval-plan-cache/index.py \\
        --dispatches tests/fixtures/sample-dispatches.jsonl \\
        --out scripts/eval-plan-cache/plan-index.jsonl \\
        --dry-run

    # Build index from real telemetry:
    python scripts/eval-plan-cache/index.py \\
        --dispatches /path/to/dispatches.jsonl \\
        --out scripts/eval-plan-cache/plan-index.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Signature extraction
# ---------------------------------------------------------------------------

def _coarsen_target(tool: str, target: str) -> str:
    """Reduce a raw tool target to a coarse, reusable form.

    Rules:
    - Bash: take the first whitespace-separated token (the command verb).
      Strip leading path characters so ``/usr/bin/python`` → ``python``.
    - All others (Read, Write, Edit, etc.): take the leading path component.
      ``internal/cache/manager.go`` → ``internal/``
      ``~/.claude/hooks/foo.sh``   → ``~/``
      ``docs/research/foo.md``     → ``docs/``
      Bare filenames (no slash)    → kept as-is (e.g. ``Makefile``)
    """
    if tool == "Bash":
        verb = target.strip().split()[0] if target.strip() else ""
        # strip leading path (e.g. /usr/bin/python → python)
        verb = os.path.basename(verb)
        return verb.lower()

    # File path: keep only the top-level component + trailing slash
    # to signal "this is a directory prefix, not a full path".
    target = target.strip()
    parts = re.split(r"[/\\]", target)
    if len(parts) > 1:
        return parts[0].lower().rstrip("~") + "/"
    return parts[0].lower()


def extract_signature(tool_calls: list[dict[str, str]]) -> str:
    """Return the plan signature for a list of tool-call dicts.

    Each dict must have ``tool`` and ``target`` keys.  Missing keys are
    silently skipped.  An empty tool-call list produces an empty string.

    The signature is deterministic and stable: same sequence → same string.
    """
    parts: list[str] = []
    for call in tool_calls:
        tool = call.get("tool", "").strip()
        target = call.get("target", "").strip()
        if not tool:
            continue
        coarse = _coarsen_target(tool, target)
        parts.append(f"{tool}:{coarse}")
    return "|".join(parts)


def signature_hash(sig: str) -> str:
    """Return a short hex digest of the signature (for exact-match lookup)."""
    return hashlib.sha256(sig.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Response summary helper
# ---------------------------------------------------------------------------

def _truncate(text: str, max_chars: int = 120) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


# ---------------------------------------------------------------------------
# Embedding (optional — skipped in --dry-run mode)
# ---------------------------------------------------------------------------

_EMBED_MODEL = "all-MiniLM-L6-v2"


def load_encoder(dry_run: bool):
    """Return a callable ``encode(texts) -> list[list[float]]`` or None."""
    if dry_run:
        return None
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        model = SentenceTransformer(_EMBED_MODEL)
        return model.encode
    except ImportError:
        print(
            "WARNING: sentence-transformers not installed.  "
            "Falling back to dry-run mode (no embeddings).  "
            "Install with: pip install sentence-transformers",
            file=sys.stderr,
        )
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_index(
    dispatches_path: Path,
    out_path: Path,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Build the plan-cache index from a JSONL dispatches file.

    Returns the list of index records (also written to *out_path*).

    Index record schema
    -------------------
    Each output JSONL line has:
      - dispatch_id       : str   — unique identifier from the source record
      - ts                : str   — ISO timestamp
      - user_query        : str   — the original user request
      - agent             : str   — which citizen/worker handled it
      - task_type         : str   — build | read | prose | test | …
      - plan_signature    : str   — pipe-separated coarse tool-call sequence
      - signature_hash    : str   — 16-char hex digest (for exact-match index)
      - response_summary  : str   — short description of what was done
      - query_embedding   : list  — float32 vector (empty list in --dry-run)
    """
    encode = load_encoder(dry_run)

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with dispatches_path.open() as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(
                    f"WARNING: line {lineno}: JSON parse error ({exc}) — skipped",
                    file=sys.stderr,
                )
                continue

            dispatch_id = obj.get("dispatch_id", f"line-{lineno}")
            if dispatch_id in seen_ids:
                print(
                    f"WARNING: duplicate dispatch_id '{dispatch_id}' at line {lineno} — skipped",
                    file=sys.stderr,
                )
                continue
            seen_ids.add(dispatch_id)

            user_query = obj.get("user_query", "")
            tool_calls: list[dict] = obj.get("tool_calls", [])
            sig = extract_signature(tool_calls)

            record: dict[str, Any] = {
                "dispatch_id": dispatch_id,
                "ts": obj.get("ts", ""),
                "user_query": user_query,
                "agent": obj.get("agent", ""),
                "task_type": obj.get("task_type", ""),
                "plan_signature": sig,
                "signature_hash": signature_hash(sig),
                "response_summary": _truncate(obj.get("response_summary", "")),
                "query_embedding": [],
            }
            records.append(record)

    if not records:
        print("ERROR: no records loaded from dispatches file", file=sys.stderr)
        sys.exit(1)

    # Embed all queries in one batch (fast on CPU with MiniLM)
    if encode is not None:
        queries = [r["user_query"] for r in records]
        print(f"Encoding {len(queries)} queries with {_EMBED_MODEL}…", file=sys.stderr)
        embeddings = encode(queries, show_progress_bar=False)
        for record, emb in zip(records, embeddings):
            record["query_embedding"] = emb.tolist()
    else:
        print(
            f"Dry-run mode: skipping embeddings for {len(records)} records.",
            file=sys.stderr,
        )

    # Write index
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")

    print(
        f"Index written: {out_path}  ({len(records)} records)",
        file=sys.stderr,
    )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a plan-cache index from historical Blackrim dispatches."
    )
    parser.add_argument(
        "--dispatches",
        default="tests/fixtures/sample-dispatches.jsonl",
        help=(
            "Path to JSONL dispatches file.  Default: tests/fixtures/sample-dispatches.jsonl "
            "(the bundled fixture; suitable for CI --dry-run)."
        ),
    )
    parser.add_argument(
        "--out",
        default="scripts/eval-plan-cache/plan-index.jsonl",
        help="Output JSONL index path.  Created if absent.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Skip embedding model load; write index with empty query_embedding vectors. "
            "Suitable for CI environments without sentence-transformers installed."
        ),
    )
    args = parser.parse_args()

    dispatches_path = Path(args.dispatches)
    if not dispatches_path.exists():
        sys.exit(f"ERROR: dispatches file not found: {dispatches_path}")

    out_path = Path(args.out)
    records = build_index(dispatches_path, out_path, dry_run=args.dry_run)
    print(f"Done. {len(records)} index records at {out_path}")


if __name__ == "__main__":
    main()
