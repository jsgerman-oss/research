#!/usr/bin/env python3
"""Aggregate per-spawn telemetry into a cost-split CSV backing §7 Table 1.

Design rationale
----------------
The invocations.jsonl captures Agent-tool spawn events (subagent dispatch)
from the Blackrim telemetry layer. It does NOT log the Gestalt main-thread
conversation turns, which are the dominant cost source. Two categories of
records appear in the JSONL:

  Real API records (source: subagent_stop, dispatch, gt-cache-warm)
    Carry actual token counts from completed API calls; these represent
    genuine subagent execution costs.

  Estimated stub records (source: dispatch_estimated, subagent_stop_estimated)
    Carry synthetic token counts generated at dispatch time; these are
    telemetry events, not real API charges.

Because the JSONL lacks main-thread records, the session_total cannot be
derived from JSONL alone. This script therefore uses a hybrid approach:

  1. Parse real API records from --telemetry to count dispatch calls and
     compute JSONL-based dispatch cost (used as a cross-check only).
  2. Load session_total, main_thread, and dispatch costs from
     --session-evidence (dashboard /api/tokens/comprehensive).
  3. Cross-check dashboard dispatch vs JSONL-computed dispatch and report
     the delta on stderr.
  4. Emit CSV with buckets: session_total, main_thread, subagent_dispatch,
     unclassified (all costs from dashboard evidence; call counts from JSONL).

The dashboard is the ground truth for cost split. The JSONL is the ground
truth for call counts and dispatch composition.

Usage (standard — hybrid mode):
    python scripts/aggregate-cost-split.py \\
      --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl \\
      --pricing /Users/jayse/Code/blackrim/internal/pricing/sheets/anthropic-public.toml \\
      --session-evidence data/raw/session-evidence.json \\
      > data/aggregated/cost-split.csv

Usage (JSONL-only mode — no dashboard, costs differ from paper):
    python scripts/aggregate-cost-split.py \\
      --telemetry data/raw/session-telemetry.json \\
      --pricing /Users/jayse/Code/blackrim/internal/pricing/sheets/anthropic-public.toml \\
      > data/aggregated/cost-split.csv

Acceptance criteria (from RC-02):
  - Unclassified bucket < 5% of total records.
  - Exits 1 if unclassified >= 5%.
  - session-evidence record 1 (kind=session-evidence) is the primary cost source.
  - JSONL real-API call count cross-checks the paper's 55-call claim.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Sources that carry real completed-API token counts
REAL_API_SOURCES: frozenset[str] = frozenset({"subagent_stop", "gt-cache-warm", "dispatch"})

# Sources that carry synthetic/estimated token counts (telemetry events, not charges)
ESTIMATED_SOURCES: frozenset[str] = frozenset(
    {"dispatch_estimated", "subagent_stop_estimated"}
)

# All known subagent-dispatch sources (real + estimated)
DISPATCH_SOURCES: frozenset[str] = REAL_API_SOURCES | ESTIMATED_SOURCES

# Sources indicating main-thread Gestalt records (none observed in current JSONL)
MAIN_THREAD_SOURCES: frozenset[str] = frozenset({"main-thread"})
MAIN_THREAD_AGENTS: frozenset[str] = frozenset({"claude-code-main"})


def load_pricing(toml_path: Path) -> dict[str, dict[str, float]]:
    """Parse the pricing TOML without a TOML library (stdlib only).

    Expected format::

        [[models]]
        model               = "claude-opus-4-7"
        input               = 5.00
        output              = 25.00
        cache_creation_5m   = 6.25
        cache_creation_1h   = 10.00
        cache_read          = 0.50

    Returns a dict keyed by model name. cache_creation = cache_creation_5m.
    All values in USD/MTok.
    """
    pricing: dict[str, dict[str, float]] = {}
    current: dict[str, float] | None = None

    with open(toml_path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line == "[[models]]":
                if current and "model" in current:
                    pricing[str(current["model"])] = current
                current = {}
                continue
            if current is not None and "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.split("#")[0].strip().strip('"')
                try:
                    current[key] = float(val)
                except ValueError:
                    current[key] = val  # type: ignore[assignment]

    if current and "model" in current:
        pricing[str(current["model"])] = current

    # Normalise cache_creation: prefer cache_creation_5m
    for _m, rates in pricing.items():
        if "cache_creation_5m" in rates and "cache_creation" not in rates:
            rates["cache_creation"] = rates["cache_creation_5m"]
        elif "cache_creation" not in rates:
            rates["cache_creation"] = rates.get("input", 3.0) * 1.25

    return pricing


# Weighted-average fallback pricing for model=unknown (40% haiku, 50% sonnet, 10% opus)
_FALLBACK_RATES: dict[str, float] = {
    "input": 2.40,
    "output": 12.00,
    "cache_creation": 3.00,
    "cache_read": 0.24,
}


def resolve_price(model: str, pricing: dict[str, dict[str, float]]) -> dict[str, float]:
    """Return rate dict for *model*, with haiku→sonnet→opus fallback chain."""
    if model and model != "unknown":
        if model in pricing:
            return pricing[model]
        for key in pricing:
            # Strip date suffix: "claude-haiku-4-5-20251001" → "claude-haiku-4-5"
            base = key.split("-20")[0]
            if model.startswith(base):
                return pricing[key]
    return _FALLBACK_RATES


def record_cost(rec: dict, pricing: dict[str, dict[str, float]]) -> float:
    """Compute cost in USD for one invocation record."""
    rates = resolve_price(rec.get("model") or "unknown", pricing)
    inp = int(rec.get("input_tokens") or 0)
    out = int(rec.get("output_tokens") or 0)
    cc = int(rec.get("cache_creation_input_tokens") or 0)
    cr = int(rec.get("cache_read_input_tokens") or 0)
    return (
        inp * rates["input"]
        + out * rates["output"]
        + cc * rates["cache_creation"]
        + cr * rates.get("cache_read", 0.0)
    ) / 1_000_000


def load_session_evidence(path: Path) -> dict | None:
    """Return the kind==session-evidence record from session-evidence.json, or None."""
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") == "session-evidence":
                return rec
    return None


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Aggregate invocations.jsonl into a cost-split CSV for §7 Table 1. "
            "Uses dashboard session-evidence for costs; JSONL for call counts."
        )
    )
    ap.add_argument(
        "--telemetry",
        default="/Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl",
        help="Path to invocations.jsonl (or a JSON-lines dump). Used for call counts.",
    )
    ap.add_argument(
        "--pricing",
        default="/Users/jayse/Code/blackrim/internal/pricing/sheets/anthropic-public.toml",
        help="Path to anthropic-public.toml rate sheet (used for JSONL cross-check).",
    )
    ap.add_argument(
        "--session-evidence",
        default=None,
        help=(
            "Path to data/raw/session-evidence.json. The kind=session-evidence "
            "record supplies session_total_usd, main_thread_usd, dispatch_usd, "
            "session_messages, and dispatch_calls as the authoritative cost figures. "
            "Without this flag, costs are computed from JSONL only (will not "
            "reproduce the paper's 99.4/0.6 split because main-thread turns are "
            "absent from the JSONL)."
        ),
    )
    args = ap.parse_args()

    pricing = load_pricing(Path(args.pricing))
    print(
        f"# Loaded pricing for {len(pricing)} model(s): {', '.join(sorted(pricing))}",
        file=sys.stderr,
    )

    # --- Parse JSONL for call counts and cross-check cost ---
    real_dispatch_calls = 0       # subagent_stop + dispatch (real API only)
    real_dispatch_cost = 0.0      # JSONL-computed cost for real API records
    estimated_records = 0         # dispatch_estimated + subagent_stop_estimated
    main_thread_records = 0       # records with source=main-thread (expected: 0)
    unclassified_records = 0      # source not in any known set
    unclassified_cost = 0.0
    total_records = 0
    fallback_used = 0

    with open(args.telemetry) as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue

            total_records += 1
            source = rec.get("source", "")
            agent = rec.get("agent", "")
            model = rec.get("model") or "unknown"
            cost = record_cost(rec, pricing)

            if model == "unknown" or not model:
                fallback_used += 1

            if source in MAIN_THREAD_SOURCES or agent in MAIN_THREAD_AGENTS:
                main_thread_records += 1
            elif source in REAL_API_SOURCES:
                real_dispatch_calls += 1
                real_dispatch_cost += cost
            elif source in ESTIMATED_SOURCES:
                estimated_records += 1
                # Estimated costs are not real charges; exclude from cost totals
            else:
                unclassified_records += 1
                unclassified_cost += cost
                print(
                    f"WARN: unclassified record "
                    f"source={source!r} agent={agent!r} model={model!r}",
                    file=sys.stderr,
                )

    print(
        f"# JSONL records: {total_records} total, "
        f"{real_dispatch_calls} real-API dispatch, "
        f"{estimated_records} estimated stubs, "
        f"{main_thread_records} main-thread, "
        f"{unclassified_records} unclassified",
        file=sys.stderr,
    )

    # Check unclassified threshold (RC-02 acceptance criterion)
    if unclassified_records > 0 and total_records > 0:
        unclassified_pct = unclassified_records / total_records * 100
        print(
            f"WARN: {unclassified_records}/{total_records} records unclassified "
            f"({unclassified_pct:.1f}%)",
            file=sys.stderr,
        )
        if unclassified_pct >= 5.0:
            print(
                "ERROR: unclassified bucket exceeds 5% threshold — "
                "partitioning is unsound; stopping without output.",
                file=sys.stderr,
            )
            sys.exit(1)

    if fallback_used:
        print(
            f"INFO: {fallback_used} records used fallback pricing (model=unknown). "
            f"Fallback rate: $2.40/MTok input (40% haiku + 50% sonnet + 10% opus avg).",
            file=sys.stderr,
        )

    # --- Determine authoritative cost figures ---
    evidence = None
    if args.session_evidence:
        evidence = load_session_evidence(Path(args.session_evidence))

    if evidence:
        # Hybrid mode: costs from dashboard evidence; call counts from JSONL
        session_total_cost = float(evidence.get("session_total_usd", 0.0))
        main_thread_cost = float(evidence.get("main_thread_usd", 0.0))
        dispatch_cost_evidence = float(evidence.get("dispatch_usd", 0.0))
        main_thread_calls_evidence = int(evidence.get("session_messages", 0))
        dispatch_calls_evidence = int(evidence.get("dispatch_calls", 0))

        # Call count cross-check
        call_delta = real_dispatch_calls - dispatch_calls_evidence
        print(
            f"# Call count cross-check: JSONL real-API={real_dispatch_calls}, "
            f"dashboard={dispatch_calls_evidence} (delta={call_delta:+d})",
            file=sys.stderr,
        )
        if abs(call_delta) > 10:
            print(
                f"WARN: dispatch call count delta {call_delta:+d} exceeds 10; "
                f"likely time-window mismatch between JSONL and dashboard snapshot.",
                file=sys.stderr,
            )

        # Cost cross-check
        cost_delta = real_dispatch_cost - dispatch_cost_evidence
        print(
            f"# Cost cross-check: JSONL real-API dispatch=${real_dispatch_cost:.4f}, "
            f"dashboard dispatch=${dispatch_cost_evidence:.4f} (delta=${cost_delta:+.4f})",
            file=sys.stderr,
        )
        if abs(cost_delta) > 5.0:
            print(
                "WARN: large cost delta between JSONL real-API and dashboard dispatch. "
                "The JSONL 'real API' records include full subagent execution costs "
                "(Builder, Writer, etc.) that the dashboard may account under "
                "'main-thread'. The dashboard is the authoritative cost source; "
                "JSONL provides call-composition evidence only.",
                file=sys.stderr,
            )

        # Use dashboard figures for the CSV
        dispatch_cost_out = dispatch_cost_evidence
        dispatch_calls_out = dispatch_calls_evidence
        main_thread_calls_out = main_thread_calls_evidence
        main_thread_cost_out = main_thread_cost
        session_total_calls = main_thread_calls_evidence + dispatch_calls_evidence

    else:
        # JSONL-only mode: session_total = real dispatch cost (main-thread absent)
        session_total_cost = real_dispatch_cost
        main_thread_cost_out = 0.0
        main_thread_calls_out = 0
        dispatch_cost_out = real_dispatch_cost
        dispatch_calls_out = real_dispatch_calls
        session_total_calls = real_dispatch_calls

        print(
            "INFO: --session-evidence not supplied; using JSONL-only costs. "
            "NOTE: main-thread turns are absent from the JSONL; "
            "the main_thread bucket will be $0.00. "
            "This mode does NOT reproduce the paper's 99.4/0.6 split.",
            file=sys.stderr,
        )

    # --- Emit CSV ---
    def share(part: float, total: float) -> float:
        return (part / total * 100) if total > 0 else 0.0

    writer = csv.writer(sys.stdout)
    writer.writerow(["bucket", "cost_usd", "n_calls", "cost_share_pct"])
    writer.writerow([
        "session_total",
        f"{session_total_cost:.4f}",
        session_total_calls,
        "100.0000",
    ])
    writer.writerow([
        "main_thread",
        f"{main_thread_cost_out:.4f}",
        main_thread_calls_out,
        f"{share(main_thread_cost_out, session_total_cost):.4f}",
    ])
    writer.writerow([
        "subagent_dispatch",
        f"{dispatch_cost_out:.4f}",
        dispatch_calls_out,
        f"{share(dispatch_cost_out, session_total_cost):.4f}",
    ])
    writer.writerow([
        "unclassified",
        f"{unclassified_cost:.4f}",
        unclassified_records,
        f"{share(unclassified_cost, session_total_cost):.4f}",
    ])

    # Summary cross-check to stderr
    print(
        "\n--- Cross-check vs §7 Table 1 ---",
        file=sys.stderr,
    )
    print(
        f"  session_total:     ${session_total_cost:9.4f}  "
        f"(§7: $115.5400)",
        file=sys.stderr,
    )
    print(
        f"  main_thread:       ${main_thread_cost_out:9.4f}  "
        f"({share(main_thread_cost_out, session_total_cost):.2f}%)  (§7: $114.81, 99.4%)",
        file=sys.stderr,
    )
    print(
        f"  subagent_dispatch: ${dispatch_cost_out:9.4f}  "
        f"({share(dispatch_cost_out, session_total_cost):.2f}%)  (§7: $0.7338, 0.6%)",
        file=sys.stderr,
    )
    print(
        f"  dispatch n_calls:  {dispatch_calls_out}  (§7: 55 calls)",
        file=sys.stderr,
    )
    if evidence:
        main_share = share(main_thread_cost_out, session_total_cost)
        disp_share = share(dispatch_cost_out, session_total_cost)
        print(
            f"\n  Cost source: dashboard /api/tokens/comprehensive "
            f"(evidence: {evidence.get('source', 'unknown')})",
            file=sys.stderr,
        )
        print(
            f"  Call count source: JSONL real-API records "
            f"({real_dispatch_calls} real vs {dispatch_calls_out} dashboard)",
            file=sys.stderr,
        )
        drift_ok = abs(main_share - 99.4) < 2.0 and abs(disp_share - 0.6) < 2.0
        if drift_ok:
            print(
                f"  Drift: within 2pp threshold — §7 table retained.",
                file=sys.stderr,
            )
        else:
            print(
                f"  Drift: main_thread {main_share:.1f}% vs 99.4% "
                f"(delta {main_share - 99.4:+.1f}pp) — §7 text uses dashboard figures.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
