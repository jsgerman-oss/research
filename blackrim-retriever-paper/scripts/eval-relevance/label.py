#!/usr/bin/env python3
"""
label.py — LLM-judge labeling CLI for the retriever relevance pipeline.

Reads the hydrated candidate pool produced by hydrate.py (recommended) or the
raw pool from pool.py, calls an LLM judge for each (query_hash, doc_id) pair
not already labeled, and writes graded relevance judgements to
data/raw/relevance.jsonl.

Usage (dry-run — no API calls, produces a stub for downstream testing):
    python scripts/eval-relevance/label.py --dry-run

Usage (gold-set mode — reads hydrated pool with real query text):
    python scripts/eval-relevance/label.py \\
        --pool blackrim-retriever-paper/data/aggregated/relevance-pool-hydrated.jsonl \\
        --dry-run

Usage (production — requires ANTHROPIC_API_KEY):
    python scripts/eval-relevance/label.py \\
        --pool blackrim-retriever-paper/data/aggregated/relevance-pool-hydrated.jsonl \\
        --out blackrim-retriever-paper/data/raw/relevance.jsonl \\
        --api-key-env ANTHROPIC_API_KEY \\
        --model claude-haiku-4-5-20251001 \\
        --cost-budget-usd 5.0 \\
        --rate-limit-rps 2.0

Gold-set mode (--gold-set-mode):
    When the pool was built by hydrate.py in gold-set mode, pass
    --gold-set-mode to skip LLM judging for pairs where a human judgment
    already exists in the gold query file.  The gold set currently marks all
    judgments as "UNMARKED" so this flag is a no-op today; it provides the
    hook for future manual annotation rounds.

Output schema (data/raw/relevance.jsonl):
    query_hash, doc_id, query_class, query_text (if available), label (0|1|2),
    model, dry_run (bool), gold_set_override (bool)

Resumability: pairs already present in --out are skipped (idempotent).
Cost gate: total estimated cost is computed before the first API call; the
    run aborts if it exceeds --cost-budget-usd.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Lazy import — the anthropic SDK is only imported when not in dry-run mode
# so the script works on systems without it installed.
_anthropic = None  # module reference, populated in _get_client()

# ---------------------------------------------------------------------------
# Pricing (USD per 1M tokens, as of model release — update as needed)
# ---------------------------------------------------------------------------
_MODEL_PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-haiku-3-20240307":   {"input": 0.25, "output": 1.25},
    "claude-sonnet-4-5":         {"input": 3.00, "output": 15.00},
}

# Rough token estimates per judge call
_EST_INPUT_TOKENS_PER_CALL = 550   # rubric + examples + query + doc snippet
_EST_OUTPUT_TOKENS_PER_CALL = 80   # brief reasoning + label digit

# Dry-run stub label
_DRY_RUN_LABEL = 1  # "marginal" — safe default for pipeline testing


def _estimate_cost(n_pairs: int, model: str) -> float:
    """Return estimated USD cost for n_pairs judge calls."""
    prices = _MODEL_PRICES.get(model, {"input": 1.0, "output": 5.0})
    input_cost = (n_pairs * _EST_INPUT_TOKENS_PER_CALL / 1_000_000) * prices["input"]
    output_cost = (n_pairs * _EST_OUTPUT_TOKENS_PER_CALL / 1_000_000) * prices["output"]
    return input_cost + output_cost


def _load_existing(out_path: Path) -> set[tuple[str, str]]:
    """Return the set of (query_hash, doc_id) pairs already labeled."""
    done: set[tuple[str, str]] = set()
    if not out_path.exists():
        return done
    with out_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                done.add((row["query_hash"], row["doc_id"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _get_client(api_key_env: str):
    """Lazily import and return an anthropic.Anthropic client."""
    global _anthropic
    if _anthropic is None:
        try:
            import anthropic as _anthropic_mod
            _anthropic = _anthropic_mod
        except ImportError:
            print(
                "error: anthropic SDK not installed. "
                "Run: pip install anthropic  (or use --dry-run)",
                file=sys.stderr,
            )
            sys.exit(1)

    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(
            f"error: environment variable {api_key_env!r} is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    return _anthropic.Anthropic(api_key=api_key)


def _call_judge(
    client,
    prompt: str,
    model: str,
) -> tuple[int | None, int, int]:
    """
    Call the LLM judge.

    Returns (label, input_tokens, output_tokens).
    label is None if the response is malformed.
    """
    from judge_prompt import parse_label  # noqa: PLC0415 — local module

    response = client.messages.create(
        model=model,
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text if response.content else ""
    label = parse_label(text)
    in_tok = getattr(response.usage, "input_tokens", 0)
    out_tok = getattr(response.usage, "output_tokens", 0)
    return label, in_tok, out_tok


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--pool",
        default="blackrim-retriever-paper/data/aggregated/relevance-pool-hydrated.jsonl",
        help=(
            "Input pool file. Default: hydrated pool from hydrate.py. "
            "Falls back to relevance-pool.jsonl if the hydrated file doesn't exist."
        ),
    )
    p.add_argument(
        "--gold-set-mode",
        action="store_true",
        default=False,
        help=(
            "When set, pairs from the gold evaluation set that already carry a "
            "human judgment (judgment != 'UNMARKED') are passed through without "
            "calling the LLM judge.  Currently a no-op because all gold judgments "
            "are 'UNMARKED'; provided as a hook for future manual annotation rounds."
        ),
    )
    p.add_argument(
        "--out",
        default="blackrim-retriever-paper/data/raw/relevance.jsonl",
        help="Output relevance judgements file.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Emit canned label=1 for every pair without making API calls. "
            "Produces a stub relevance.jsonl for downstream testing."
        ),
    )
    p.add_argument(
        "--api-key-env",
        default="ANTHROPIC_API_KEY",
        help="Name of the env var holding the Anthropic API key.",
    )
    p.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        choices=list(_MODEL_PRICES.keys()),
        help="Judge model to use.",
    )
    p.add_argument(
        "--cost-budget-usd",
        type=float,
        default=5.0,
        help="Maximum USD to spend. Script aborts if estimate exceeds this.",
    )
    p.add_argument(
        "--rate-limit-rps",
        type=float,
        default=2.0,
        help="API calls per second (for production runs).",
    )
    p.add_argument(
        "--max-pairs",
        type=int,
        default=None,
        help="Cap the number of pairs to label (useful for partial runs / spot-checks).",
    )
    args = p.parse_args()

    pool_path = Path(args.pool)
    out_path = Path(args.out)

    # Fall back to the raw pool if the hydrated file doesn't exist yet.
    raw_pool_path = Path(
        "blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl"
    )
    if not pool_path.exists() and pool_path != raw_pool_path and raw_pool_path.exists():
        print(
            f"warn: hydrated pool not found at {pool_path}; "
            f"falling back to {raw_pool_path}. "
            "Run hydrate.py first for real query text in judge prompts.",
            file=sys.stderr,
        )
        pool_path = raw_pool_path

    if not pool_path.exists():
        print(f"error: pool not found: {pool_path}", file=sys.stderr)
        print(
            "       Run hydrate.py first: "
            "python scripts/eval-relevance/hydrate.py",
            file=sys.stderr,
        )
        print(
            "       Or build the raw pool: "
            "python scripts/eval-relevance/pool.py",
            file=sys.stderr,
        )
        return 1

    is_hydrated = "hydrated" in pool_path.name

    # Load pool
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
        return 1

    if is_hydrated:
        n_with_text = sum(1 for r in pool if r.get("doc_available"))
        print(
            f"hydrated pool: {len(pool)} pairs | "
            f"{n_with_text} with resolved doc text | "
            f"{len(pool) - n_with_text} stubs",
            file=sys.stderr,
        )
    else:
        print(
            f"raw pool (no query/doc plaintext): {len(pool)} pairs. "
            "Run hydrate.py for better judge accuracy.",
            file=sys.stderr,
        )

    # Skip already-labeled pairs
    already_done = _load_existing(out_path)
    pending = [
        row for row in pool
        if (row["query_hash"], row["doc_id"]) not in already_done
    ]

    if args.max_pairs is not None:
        pending = pending[: args.max_pairs]

    n_pending = len(pending)
    n_already = len(already_done)

    print(
        f"pool: {len(pool)} pairs | already labeled: {n_already} | "
        f"pending: {n_pending}",
        file=sys.stderr,
    )

    if n_pending == 0:
        print("Nothing to label — all pairs already in output.", file=sys.stderr)
        return 0

    # Cost estimation (always, even for dry-run — for informational output)
    est_cost = _estimate_cost(n_pending, args.model)
    print(
        f"estimated cost: ${est_cost:.4f} "
        f"({n_pending} pairs × ~{_EST_INPUT_TOKENS_PER_CALL} in + "
        f"{_EST_OUTPUT_TOKENS_PER_CALL} out tokens @ {args.model})",
        file=sys.stderr,
    )

    if not args.dry_run and est_cost > args.cost_budget_usd:
        print(
            f"error: estimated cost ${est_cost:.4f} exceeds budget "
            f"${args.cost_budget_usd:.2f}. Use --cost-budget-usd to raise "
            f"the limit or --max-pairs to reduce scope.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print("dry-run mode: emitting canned label=1 for all pending pairs.", file=sys.stderr)

    # Production: build client and import judge_prompt
    client = None
    if not args.dry_run:
        # Add script directory to path so judge_prompt can be imported
        sys.path.insert(0, str(Path(__file__).parent))
        client = _get_client(args.api_key_env)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    min_interval = 1.0 / args.rate_limit_rps if not args.dry_run else 0.0
    n_labeled = 0
    n_malformed = 0
    n_gold_passthrough = 0
    total_in_tokens = 0
    total_out_tokens = 0
    actual_cost = 0.0

    with out_path.open("a") as g:
        for i, row in enumerate(pending):
            qhash = row["query_hash"]
            doc_id = row["doc_id"]
            qclass = row.get("query_class", "unknown")
            # Hydrated pool carries plaintext; raw pool does not.
            query_text = row.get("query_text") or f"[query_hash={qhash}, class={qclass}]"
            doc_text = row.get("doc_text") or f"[doc_id={doc_id}]"
            gold_set_override = False

            if args.dry_run:
                label = _DRY_RUN_LABEL
                in_tok = _EST_INPUT_TOKENS_PER_CALL
                out_tok = _EST_OUTPUT_TOKENS_PER_CALL
            elif args.gold_set_mode and row.get("source") == "gold-set":
                # Future hook: when the gold set carries human judgments
                # (judgment != 'UNMARKED'), pass them through without an LLM call.
                # Currently all judgments are UNMARKED so this never fires, but the
                # path is ready for manual annotation rounds.
                gold_judgment = row.get("judgment", "UNMARKED")
                if gold_judgment not in ("UNMARKED", "", None):
                    _LABEL_MAP = {"NOT_RELEVANT": 0, "PARTIAL": 1, "RELEVANT": 2}
                    mapped = _LABEL_MAP.get(str(gold_judgment).upper())
                    if mapped is not None:
                        label = mapped
                        in_tok = 0
                        out_tok = 0
                        gold_set_override = True
                        n_gold_passthrough += 1
                    else:
                        # Unrecognised judgment string — fall through to LLM judge.
                        gold_set_override = False

                if not gold_set_override:
                    # Gold pair but judgment is UNMARKED — call the LLM judge.
                    from judge_prompt import build_prompt  # noqa: PLC0415
                    prompt = build_prompt(query_text, doc_text)
                    t0 = time.monotonic()
                    label, in_tok, out_tok = _call_judge(client, prompt, args.model)
                    elapsed = time.monotonic() - t0
                    if label is None:
                        n_malformed += 1
                        label = _DRY_RUN_LABEL
                        print(
                            f"  warn: malformed judge response for "
                            f"({qhash}, {doc_id}) — defaulting to {label}",
                            file=sys.stderr,
                        )
                    sleep_for = max(0.0, min_interval - elapsed)
                    if sleep_for > 0:
                        time.sleep(sleep_for)
            else:
                # Standard LLM judge path.  Uses plaintext from hydrated pool
                # when available; falls back to hash/slug stubs for raw pool.
                from judge_prompt import build_prompt  # noqa: PLC0415
                prompt = build_prompt(query_text, doc_text)

                t0 = time.monotonic()
                label, in_tok, out_tok = _call_judge(client, prompt, args.model)
                elapsed = time.monotonic() - t0

                if label is None:
                    n_malformed += 1
                    label = _DRY_RUN_LABEL  # fallback to marginal on parse failure
                    print(
                        f"  warn: malformed judge response for "
                        f"({qhash}, {doc_id}) — defaulting to {label}",
                        file=sys.stderr,
                    )

                # Rate limiting
                sleep_for = max(0.0, min_interval - elapsed)
                if sleep_for > 0:
                    time.sleep(sleep_for)

            total_in_tokens += in_tok
            total_out_tokens += out_tok

            prices = _MODEL_PRICES.get(args.model, {"input": 1.0, "output": 5.0})
            pair_cost = (
                (in_tok / 1_000_000) * prices["input"]
                + (out_tok / 1_000_000) * prices["output"]
            )
            actual_cost += pair_cost

            out_row = {
                "query_hash": qhash,
                "doc_id": doc_id,
                "query_class": qclass,
                "query_text": query_text,
                "label": label,
                "model": args.model if not args.dry_run else "dry-run",
                "dry_run": args.dry_run,
                "gold_set_override": gold_set_override,
            }
            g.write(json.dumps(out_row) + "\n")
            n_labeled += 1

            if (i + 1) % 50 == 0:
                print(
                    f"  {i + 1}/{n_pending} labeled | "
                    f"actual cost so far: ${actual_cost:.4f}",
                    file=sys.stderr,
                )

    print(
        f"done: {n_labeled} pairs labeled | "
        f"{n_malformed} malformed responses | "
        f"{n_gold_passthrough} gold-set passthroughs | "
        f"total tokens: {total_in_tokens} in / {total_out_tokens} out | "
        f"actual cost: ${actual_cost:.4f} | "
        f"output: {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
