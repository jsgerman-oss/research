"""
rubric.py — pure-Python string-match scorer for the TRIM-03 fidelity eval.

Each prompt in prompts.yml declares:
  expected_substrings:  strings that MUST appear in the response
  forbidden_substrings: strings that must NOT appear in the response

Scoring per prompt
------------------
  hit_expected   = number of expected substrings found in the response
  hit_forbidden  = number of forbidden substrings found in the response
  pass           = (hit_expected == total_expected) AND (hit_forbidden == 0)
  score          = hit_expected / total_expected   if hit_forbidden == 0
                 = 0.0                             if any forbidden hit

Status values
-------------
  pass      — all expected matched, no forbidden matched
  fail      — one or more expected missing OR one or more forbidden matched
  unscored  — prompt entry malformed or response is empty/None
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RubricResult:
    prompt_id: str
    dimension: str
    hit_expected: int
    total_expected: int
    hit_forbidden: int
    total_forbidden: int
    score: float
    status: str          # "pass" | "fail" | "unscored"
    notes: str = ""


def _contains(text: str, substring: str) -> bool:
    """Case-insensitive substring check."""
    return substring.lower() in text.lower()


def score_response(
    prompt_id: str,
    dimension: str,
    response_text: Optional[str],
    expected_substrings: list[str],
    forbidden_substrings: list[str],
) -> RubricResult:
    """
    Score a single model response against its rubric.

    Parameters
    ----------
    prompt_id:           identifier from prompts.yml (e.g. "worktree-01")
    dimension:           one of worktree-isolation | delegation | commit-path | merge-flow
    response_text:       raw text of the model's response; None or "" → unscored
    expected_substrings: substrings that must appear
    forbidden_substrings: substrings that must not appear
    """
    if not response_text or not response_text.strip():
        return RubricResult(
            prompt_id=prompt_id,
            dimension=dimension,
            hit_expected=0,
            total_expected=len(expected_substrings),
            hit_forbidden=0,
            total_forbidden=len(forbidden_substrings),
            score=0.0,
            status="unscored",
            notes="empty or None response",
        )

    hit_expected = sum(
        1 for s in expected_substrings if _contains(response_text, s)
    )
    hit_forbidden = sum(
        1 for s in forbidden_substrings if _contains(response_text, s)
    )

    total_expected = len(expected_substrings)
    total_forbidden = len(forbidden_substrings)

    if total_expected == 0:
        # No expected checks — only forbidden can fail it
        raw_score = 1.0
    else:
        raw_score = hit_expected / total_expected

    if hit_forbidden > 0:
        raw_score = 0.0

    passed = (hit_expected == total_expected) and (hit_forbidden == 0)
    status = "pass" if passed else "fail"

    notes_parts = []
    if hit_expected < total_expected:
        missing = [
            s for s in expected_substrings if not _contains(response_text, s)
        ]
        notes_parts.append(f"missing_expected={missing}")
    if hit_forbidden > 0:
        found_forbidden = [
            s for s in forbidden_substrings if _contains(response_text, s)
        ]
        notes_parts.append(f"found_forbidden={found_forbidden}")

    return RubricResult(
        prompt_id=prompt_id,
        dimension=dimension,
        hit_expected=hit_expected,
        total_expected=total_expected,
        hit_forbidden=hit_forbidden,
        total_forbidden=total_forbidden,
        score=round(raw_score, 4),
        status=status,
        notes="; ".join(notes_parts),
    )


def score_all(
    prompts: list[dict],
    responses: dict[str, str],
) -> list[RubricResult]:
    """
    Score all prompts.

    Parameters
    ----------
    prompts:   list of prompt dicts loaded from prompts.yml
    responses: mapping from prompt_id → response_text
               (for dry-run, all values are "DRY_RUN")
    """
    results = []
    for entry in prompts:
        pid = entry.get("id", "")
        dim = entry.get("dimension", "")
        expected = entry.get("expected_substrings") or []
        forbidden = entry.get("forbidden_substrings") or []

        if not pid:
            continue  # skip malformed entries

        response_text = responses.get(pid)
        result = score_response(
            prompt_id=pid,
            dimension=dim,
            response_text=response_text,
            expected_substrings=expected,
            forbidden_substrings=forbidden,
        )
        results.append(result)

    return results
