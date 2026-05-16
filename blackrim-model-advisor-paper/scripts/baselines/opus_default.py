"""
opus_default.py — opus-default baseline policy.

Always recommends opus (tier 2) regardless of agent or task shape.
This represents the conservative upper bound: maximum capability
at maximum cost.  It is the implicit policy many users apply before
any model-optimization advisor is in place.

Tier encoding
-------------
    0 = haiku, 1 = sonnet, 2 = opus
"""
from __future__ import annotations

_OPUS_TIER: int = 2


def select(agent: str, shape: str) -> int:  # noqa: ARG001
    """Always return opus.

    Parameters
    ----------
    agent:
        Agent name — accepted for API compatibility; not used.
    shape:
        Task-shape code — accepted for API compatibility; not used.

    Returns
    -------
    int
        Always 2 (opus).
    """
    return _OPUS_TIER
