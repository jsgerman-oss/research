"""
static_frontmatter.py — static-frontmatter baseline policy.

Dispatches every request based on a fixed (agent, shape) → tier lookup
table. This simulates a human operator who has read the CLAUDE.md
dispatch table once and applies it rigidly without any adaptive update.

Tier encoding (matches the rest of the paper):
    0 = haiku   (cheapest)
    1 = sonnet  (mid)
    2 = opus    (most capable / most expensive)

Table design rationale
----------------------
- architect     → opus  everywhere: architecture decisions are load-bearing
                  and asymmetric risk justifies the cost premium.
- writer        → haiku everywhere: prose generation at fixed spec is
                  well-suited to small models; the CLAUDE.md table confirms.
- researcher    → haiku everywhere: fast lookups, read-only; haiku's
                  throughput advantage dominates.
- builder       → sonnet everywhere: multi-file edits with clear spec;
                  sonnet has the code-quality headroom to handle the long
                  context without opus overhead.
- reviewer      → sonnet everywhere: line-by-line code review; sonnet
                  provides sufficient reasoning depth.
- tester        → sonnet everywhere: test authoring with known patterns;
                  sonnet is the established default for this work type.

For any (agent, shape) combination not in the table, the policy falls
back to sonnet (a conservative mid-tier default).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Dispatch table: agent name (case-insensitive) → tier int
# Shape is ignored by this policy — it uses agent identity alone, which
# matches the original CLAUDE.md delegation-discipline table that makes no
# per-shape distinction within a given worker role.
# ---------------------------------------------------------------------------
_AGENT_TO_TIER: dict[str, int] = {
    "architect":  2,  # opus
    "writer":     0,  # haiku
    "researcher": 0,  # haiku
    "builder":    1,  # sonnet
    "reviewer":   1,  # sonnet
    "tester":     1,  # sonnet
}

# Fall-back tier for any agent not listed above.
_DEFAULT_TIER: int = 1  # sonnet


def select(agent: str, shape: str) -> int:  # noqa: ARG001  (shape unused here)
    """Return the static tier for this (agent, shape) pair.

    Parameters
    ----------
    agent:
        Agent name as recorded in `advisor-decisions.jsonl` (e.g. "Builder").
    shape:
        Task-shape code (e.g. "Bu1").  Not used by this policy; accepted
        for API compatibility with the other baselines.

    Returns
    -------
    int
        0 (haiku), 1 (sonnet), or 2 (opus).
    """
    return _AGENT_TO_TIER.get(agent.lower(), _DEFAULT_TIER)
