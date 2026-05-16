#!/usr/bin/env python3
"""
hydrate.py — Hydrate the relevance pool with plaintext query text and doc snippets.

The retrieval pipeline records queries as SHA-256[:16] hashes (privacy-preserving)
and doc_ids as bd memory slugs.  Before the LLM judge can produce meaningful
relevance labels, both need to be resolved to plaintext.

Two operating modes:

  --gold-set-mode (DEFAULT)
      Uses the 30 hand-curated evaluation queries from Blackrim's eval set
      (/Users/jayse/Code/blackrim/evals/embedding-retrieval/queries.jsonl).
      Runs each query against the bd memory corpus via ``bd recall`` to fetch
      candidate docs, then emits a hydrated pool.  This is the authoritative
      evaluation corpus for the paper.

  --production-mode
      Joins the existing relevance-pool.jsonl (built from 978 operational
      telemetry records) with plaintext via ``bd recall`` on each doc_id.
      Use this for characterising production query traffic, not for NDCG
      evaluation.

The 30/978 split:
  * 30 gold queries  — hand-curated for coverage of all 6 query classes.
                       These drive the paper's NDCG evaluation.
  * 978 telemetry records — real production traffic, hash-only, no plaintext.
                            Used for operational characterisation (latency,
                            class distribution, scorer coverage) only.

Output schema (data/aggregated/relevance-pool-hydrated.jsonl):
  One row per (query_hash, doc_id) candidate pair:
    query_hash   str   SHA-256[:16] of the query
    query_text   str   Plaintext query (resolved from gold set or stub)
    query_type   str   Query class from gold set (or 'unknown')
    query_class  str   Operational class from paper_stream classifyQuery
    doc_id       str   bd memory slug
    doc_text     str   Memory content (resolved via bd recall, or stub)
    doc_available bool  True when doc_text was resolved from the live corpus
    found_by     list  Scorers that returned this doc (production mode only)
    scores       dict  Scorer scores (production mode only)
    min_rank     int   Best rank across scorers (production mode only)
    source       str   'gold-set' or 'production'

Usage:
    # Gold-set mode (default — builds eval pool from 30 curated queries):
    python blackrim-retriever-paper/scripts/eval-relevance/hydrate.py

    # Production mode (joins operational pool with doc text):
    python blackrim-retriever-paper/scripts/eval-relevance/hydrate.py \\
        --production-mode \\
        --pool blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Gold evaluation set — 30 hand-curated queries with type annotations.
# Produced by the Blackrim project team for retriever evaluation.
_GOLD_QUERIES_PATH = Path(
    "/Users/jayse/Code/blackrim/evals/embedding-retrieval/queries.jsonl"
)

# Where to find the bd binary (same one used by the main Blackrim workflow).
# Override with --bd-bin if it's not on PATH.
_DEFAULT_BD_BIN = "bd"

# Working directory for bd recall calls — must be the Blackrim project root
# so bd finds the right .beads/ store.
_BLACKRIM_ROOT = Path("/Users/jayse/Code/blackrim")

# Snippet length cap (characters).  The LLM judge prompt template expects
# ~220 words / ~300 tokens of doc context; 1200 chars is a safe upper bound.
_DOC_SNIPPET_MAX_CHARS = 1200

# Stub text emitted when a doc cannot be resolved from the live corpus.
_DOC_STUB = "[doc snippet unavailable — bd recall returned no content for this slug]"


# ---------------------------------------------------------------------------
# Query-type → paper class mapping
# ---------------------------------------------------------------------------
# The gold set uses fine-grained type labels.  We map them to the 6 query
# classes described in the paper so the hydrated pool carries consistent
# class labels for NDCG stratification.
#
# Paper classes:
#   technical-lookup    — parameter / algorithm detail queries
#   failure-recall      — queries targeting [failure]-tagged memories
#   agent-scoped        — queries filtered by agent prefix
#   continuity          — session-resumption / recency-primary queries
#   concept-bridge      — semantic similarity / paraphrase queries
#   exact-id-or-slug    — bd id / config-key exact lookups
#   other               — queries that don't fit the above six

_TYPE_TO_PAPER_CLASS: dict[str, str] = {
    "technical_lookup":   "technical-lookup",
    "technical_detail":   "technical-lookup",
    "technical":          "technical-lookup",
    "algorithm":          "technical-lookup",
    "literature":         "technical-lookup",
    "performance_question": "technical-lookup",
    "failure_recall":     "failure-recall",
    "agent_scoped":       "agent-scoped",
    "continuity":         "continuity",
    "concept_bridge":     "concept-bridge",
    "exact_id":           "exact-id-or-slug",
    "configuration":      "exact-id-or-slug",
    "cli_reference":      "exact-id-or-slug",
    "reference":          "exact-id-or-slug",
    "code_lookup":        "technical-lookup",
    "system_design":      "technical-lookup",
    "system_data":        "technical-lookup",
    "architecture":       "concept-bridge",
    "component":          "concept-bridge",
    "feature":            "concept-bridge",
}


def _map_type(raw_type: str) -> str:
    return _TYPE_TO_PAPER_CLASS.get(raw_type, "other")


# ---------------------------------------------------------------------------
# Query hashing (mirrors internal/bdmemory/paper_stream.go HashQuery)
# ---------------------------------------------------------------------------

def _hash_query(query: str) -> str:
    """Return SHA-256[:16] of the query, matching the Go HashQuery function."""
    if not query:
        return ""
    return hashlib.sha256(query.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Doc-snippet resolution via bd recall
# ---------------------------------------------------------------------------

def _fetch_doc_snippet(slug: str, bd_bin: str, blackrim_root: Path = _BLACKRIM_ROOT) -> tuple[str, bool]:
    """
    Fetch the content of a bd memory by slug.

    Returns (snippet, available) where:
      snippet    — first _DOC_SNIPPET_MAX_CHARS of the memory body, or _DOC_STUB
      available  — True when the memory was found and returned non-empty content

    Uses ``bd recall <slug>`` in the Blackrim project root.  bd recall exits 0
    and prints the memory body on success; exits non-zero or prints an error
    message on failure.

    TODO: fetch_doc_snippet() will be replaceable with a direct (doc_id → snippet)
    lookup API once Blackrim exposes one (e.g. a ``bd memory get --json <slug>``
    command or an HTTP endpoint).  The current shell-out to ``bd recall`` is the
    only available surface as of 2026-05.
    """
    try:
        result = subprocess.run(
            [bd_bin, "recall", slug],
            capture_output=True,
            cwd=str(blackrim_root),
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(
            f"  warn: bd recall failed for {slug!r}: {exc}",
            file=sys.stderr,
        )
        return _DOC_STUB, False

    text = result.stdout.decode("utf-8", errors="replace").strip()

    # bd recall prints "No memory with key ..." to stdout on miss.
    if not text or text.startswith("No memory with key"):
        return _DOC_STUB, False

    snippet = text[:_DOC_SNIPPET_MAX_CHARS]
    return snippet, True


# ---------------------------------------------------------------------------
# Gold-set pool builder
# ---------------------------------------------------------------------------

def _build_gold_pool(
    gold_path: Path,
    bd_bin: str,
    blackrim_root: Path = _BLACKRIM_ROOT,
    verbose: bool = False,
) -> list[dict]:
    """
    Build a relevance pool from the 30-record gold evaluation set.

    For each gold query:
      1. Compute its query_hash.
      2. Iterate over all bd memory slugs that exist in the live corpus.
      3. Emit one pool row per (query, doc) pair — label.py will judge them.

    This is a cross-product approach: with 30 queries × N docs we get 30×N
    candidates.  pool.py uses top-k scorer results to limit this; in gold-set
    mode we include all docs in the live corpus so the judge can assign 0/1/2
    labels and NDCG can be computed with full recall.

    NOTE: When the memory corpus is large, this becomes expensive for the LLM
    judge.  For the current ~42-memory corpus the cost is negligible (< $0.01
    at haiku pricing).  Add --max-docs-per-query to cap if needed.
    """
    if not gold_path.exists():
        print(
            f"error: gold queries not found at {gold_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    gold_queries: list[dict] = []
    with gold_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                gold_queries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not gold_queries:
        print("error: gold query file is empty", file=sys.stderr)
        sys.exit(1)

    print(
        f"gold set: {len(gold_queries)} queries loaded from {gold_path}",
        file=sys.stderr,
    )

    # Enumerate all bd memory slugs in the Blackrim project.
    slug_corpus = _list_memory_slugs(bd_bin, blackrim_root=blackrim_root)
    if not slug_corpus:
        print(
            "warn: no bd memories found — pool will contain stub doc rows only.",
            file=sys.stderr,
        )

    print(
        f"memory corpus: {len(slug_corpus)} slugs available",
        file=sys.stderr,
    )

    # Fetch all doc snippets up front to avoid redundant bd recall calls.
    doc_cache: dict[str, tuple[str, bool]] = {}
    for slug in slug_corpus:
        if verbose:
            print(f"  fetching doc: {slug}", file=sys.stderr)
        doc_cache[slug] = _fetch_doc_snippet(slug, bd_bin, blackrim_root=blackrim_root)

    # Emit one row per (query, doc) pair.
    rows: list[dict] = []
    for gq in gold_queries:
        query_text = gq.get("query", "")
        raw_type = gq.get("type", "unknown")
        query_hash = _hash_query(query_text)
        paper_class = _map_type(raw_type)

        for slug in slug_corpus:
            doc_text, doc_available = doc_cache[slug]
            rows.append({
                "query_hash": query_hash,
                "query_text": query_text,
                "query_type": raw_type,
                "query_class": paper_class,
                "doc_id": slug,
                "doc_text": doc_text,
                "doc_available": doc_available,
                "found_by": [],
                "scores": {},
                "min_rank": -1,
                "source": "gold-set",
            })

    return rows


def _list_memory_slugs(bd_bin: str, blackrim_root: Path = _BLACKRIM_ROOT) -> list[str]:
    """
    Return all memory slugs in the Blackrim bd store.

    Parses ``bd memories`` output: slug lines appear before their bracketed
    tag lines (e.g. ``  my-slug\n    [Tag] body...``).  We extract lines that
    are non-empty, non-indented-tag lines.
    """
    try:
        result = subprocess.run(
            [bd_bin, "memories"],
            capture_output=True,
            cwd=str(blackrim_root),
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"warn: could not list bd memories: {exc}", file=sys.stderr)
        return []

    slugs: list[str] = []
    stdout_text = result.stdout.decode("utf-8", errors="replace")
    for line in stdout_text.splitlines():
        # Slug lines in ``bd memories`` output are indented by exactly 2 spaces.
        # Body/tag lines are indented by 4+ spaces.
        # We match exactly "  <slug>\n" — two spaces followed by a non-space token
        # with no embedded spaces (slugs are kebab-case or short alphanumeric).
        if not line.startswith("  "):
            continue
        if line.startswith("   "):  # 3+ spaces → body or tag line, skip
            continue
        candidate = line[2:].strip()
        if candidate and " " not in candidate and not candidate.startswith("Memories"):
            slugs.append(candidate)

    return slugs


# ---------------------------------------------------------------------------
# Production mode: join existing pool with doc text
# ---------------------------------------------------------------------------

def _hydrate_production_pool(
    pool_path: Path,
    bd_bin: str,
    blackrim_root: Path = _BLACKRIM_ROOT,
    verbose: bool = False,
) -> list[dict]:
    """
    Hydrate the production pool (from pool.py) with doc snippets.

    Query text cannot be recovered for production records — hashes are
    one-way.  query_text is set to a stub indicating its hash.  This mode
    is useful for characterising which docs get retrieved in production,
    but labels produced from it are lower-quality than gold-set labels.
    """
    if not pool_path.exists():
        print(f"error: pool not found: {pool_path}", file=sys.stderr)
        sys.exit(1)

    pool: list[dict] = []
    with pool_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                pool.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not pool:
        print("error: pool is empty", file=sys.stderr)
        sys.exit(1)

    print(
        f"production pool: {len(pool)} pairs loaded from {pool_path}",
        file=sys.stderr,
    )

    # Fetch doc snippets (deduplicate: many rows share the same doc_id).
    unique_slugs = list({row["doc_id"] for row in pool})
    doc_cache: dict[str, tuple[str, bool]] = {}
    for slug in unique_slugs:
        if verbose:
            print(f"  fetching doc: {slug}", file=sys.stderr)
        doc_cache[slug] = _fetch_doc_snippet(slug, bd_bin, blackrim_root=blackrim_root)

    n_available = sum(1 for _, avail in doc_cache.values() if avail)
    print(
        f"doc resolution: {n_available}/{len(unique_slugs)} slugs resolved",
        file=sys.stderr,
    )

    rows: list[dict] = []
    for row in pool:
        qhash = row["query_hash"]
        slug = row["doc_id"]
        doc_text, doc_available = doc_cache[slug]
        rows.append({
            "query_hash": qhash,
            "query_text": f"[hash-only: {qhash}]",
            "query_type": "unknown",
            "query_class": row.get("query_class", "unknown"),
            "doc_id": slug,
            "doc_text": doc_text,
            "doc_available": doc_available,
            "found_by": row.get("found_by", []),
            "scores": row.get("scores", {}),
            "min_rank": row.get("min_rank", -1),
            "source": "production",
        })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--production-mode",
        action="store_true",
        default=False,
        help=(
            "Hydrate the operational pool (pool.py output) with doc text. "
            "Query text is not recoverable in this mode. "
            "Default: gold-set mode (30 hand-curated eval queries)."
        ),
    )
    p.add_argument(
        "--gold-queries",
        default=str(_GOLD_QUERIES_PATH),
        help=f"Path to the gold eval query set. Default: {_GOLD_QUERIES_PATH}",
    )
    p.add_argument(
        "--pool",
        default="blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl",
        help="Pool file for --production-mode.",
    )
    p.add_argument(
        "--out",
        default="blackrim-retriever-paper/data/aggregated/relevance-pool-hydrated.jsonl",
        help="Output path for the hydrated pool.",
    )
    p.add_argument(
        "--bd-bin",
        default=_DEFAULT_BD_BIN,
        help="Path to the bd binary.",
    )
    p.add_argument(
        "--blackrim-root",
        default=str(_BLACKRIM_ROOT),
        help="Blackrim project root (for bd recall cwd).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print per-doc fetch progress.",
    )
    args = p.parse_args()

    blackrim_root = Path(args.blackrim_root)

    if args.production_mode:
        rows = _hydrate_production_pool(
            pool_path=Path(args.pool),
            bd_bin=args.bd_bin,
            blackrim_root=blackrim_root,
            verbose=args.verbose,
        )
    else:
        rows = _build_gold_pool(
            gold_path=Path(args.gold_queries),
            bd_bin=args.bd_bin,
            blackrim_root=blackrim_root,
            verbose=args.verbose,
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w") as g:
        for row in rows:
            g.write(json.dumps(row) + "\n")

    n_available = sum(1 for r in rows if r.get("doc_available"))
    print(
        f"wrote {len(rows)} hydrated pairs → {out_path} "
        f"({n_available} with resolved doc text, "
        f"{len(rows) - n_available} stubs)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
