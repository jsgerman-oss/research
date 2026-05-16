#!/usr/bin/env python3
"""
pool.py — Build a per-(query_hash, doc_id) candidate pool for relevance labeling.

Schema notes (from queries.jsonl inspection):
  - scorers: {scorer_name: {method, top_k, scores: [float, ...], latency_ms}}
    where scores[i] aligns positionally with final_ranks[i].doc_id.
  - final_ranks: [{doc_id, final_rank, final_score}]
  - Scorers present in production data: "keyword", "depgraph".
    "depgraph" records lack scores/final_ranks and are excluded from pooling.
  - 14 unique query_hashes across 994 records; 22 unique doc_ids.

Output schema (data/aggregated/relevance-pool.jsonl):
  One row per (query_hash, doc_id) candidate pair:
    query_hash, query_class, doc_id,
    found_by: [scorer_name, ...]    — all scorers that returned this doc
    scores:   {scorer_name: float}  — score from each scorer that returned it
    min_rank: int                   — best (lowest) rank this doc received across scorers
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def _build_pool_for_record(record: dict, top_k: int) -> list[dict]:
    """
    Extract the top-k docs from each scorer and union them into a pool.

    Returns a list of candidate dicts, one per unique doc_id seen across
    all scorers.
    """
    scorers = record.get("scorers", {})
    final_ranks = record.get("final_ranks", [])

    # Build positional doc_id list from final_ranks (sorted by rank)
    ranked_docs = sorted(final_ranks, key=lambda x: x.get("final_rank", 9999))
    doc_ids_by_pos = [fr["doc_id"] for fr in ranked_docs if "doc_id" in fr]

    # Per-doc accumulator: {doc_id: {scorer: score}}
    pool: dict[str, dict[str, float]] = defaultdict(dict)
    # Track best (lowest) rank per doc
    best_rank: dict[str, int] = {}

    for scorer_name, scorer_data in scorers.items():
        if not isinstance(scorer_data, dict):
            continue
        scores = scorer_data.get("scores", [])
        if not scores or not doc_ids_by_pos:
            # depgraph and zero-result records have no scores
            continue

        # scores[i] aligns with doc_ids_by_pos[i] positionally
        pairs = list(zip(doc_ids_by_pos, scores))
        # Take up to top_k from this scorer (docs are already ordered by rank)
        top_pairs = pairs[:top_k]

        for rank_i, (doc_id, score) in enumerate(top_pairs, start=1):
            pool[doc_id][scorer_name] = float(score)
            if doc_id not in best_rank or rank_i < best_rank[doc_id]:
                best_rank[doc_id] = rank_i

    # Flatten to list of candidate rows
    candidates = []
    for doc_id, scorer_scores in pool.items():
        candidates.append({
            "doc_id": doc_id,
            "found_by": sorted(scorer_scores.keys()),
            "scores": scorer_scores,
            "min_rank": best_rank.get(doc_id, -1),
        })

    return candidates


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--queries",
        default="blackrim-retriever-paper/data/raw/queries.jsonl",
        help="Path to queries.jsonl (paper-stream).",
    )
    p.add_argument(
        "--out",
        default="blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl",
        help="Output path for the candidate pool.",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Max results to take from each scorer per query (default: 10).",
    )
    args = p.parse_args()

    src = Path(args.queries)
    if not src.exists():
        print(f"error: queries not found: {src}", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Collapse multiple records per query_hash into a single pool.
    # The same query_hash may appear many times (repeated queries); we union
    # all doc_ids seen across all records for that hash, keeping the best score
    # per (query_hash, doc_id, scorer).
    # query_meta: {query_hash: {query_class, per_doc_scores, per_doc_best_rank}}
    query_meta: dict[str, dict] = {}

    n_records = 0
    n_skipped = 0

    with src.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                n_skipped += 1
                continue

            qhash = record.get("query_hash")
            if not qhash:
                n_skipped += 1
                continue

            n_records += 1
            qclass = record.get("query_class", "unknown")

            if qhash not in query_meta:
                query_meta[qhash] = {
                    "query_class": qclass,
                    "docs": defaultdict(dict),   # doc_id -> {scorer: best_score}
                    "best_rank": {},              # doc_id -> best rank seen
                }

            meta = query_meta[qhash]
            candidates = _build_pool_for_record(record, top_k=args.top_k)
            for cand in candidates:
                doc_id = cand["doc_id"]
                for scorer, score in cand["scores"].items():
                    existing = meta["docs"][doc_id].get(scorer)
                    if existing is None or score > existing:
                        meta["docs"][doc_id][scorer] = score
                existing_rank = meta["best_rank"].get(doc_id)
                rank = cand["min_rank"]
                if existing_rank is None or (rank > 0 and rank < existing_rank):
                    meta["best_rank"][doc_id] = rank

    # Emit one row per (query_hash, doc_id) pair
    n_pairs = 0
    with out.open("w") as g:
        for qhash, meta in sorted(query_meta.items()):
            for doc_id, scorer_scores in sorted(meta["docs"].items()):
                if not scorer_scores:
                    continue
                row = {
                    "query_hash": qhash,
                    "query_class": meta["query_class"],
                    "doc_id": doc_id,
                    "found_by": sorted(scorer_scores.keys()),
                    "scores": scorer_scores,
                    "min_rank": meta["best_rank"].get(doc_id, -1),
                }
                g.write(json.dumps(row) + "\n")
                n_pairs += 1

    print(
        f"read {n_records} records ({n_skipped} skipped), "
        f"{len(query_meta)} unique queries → {n_pairs} pool pairs → {out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
