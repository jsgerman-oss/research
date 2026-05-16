#!/usr/bin/env python3
"""
judge_prompt.py — Build graded-relevance judge prompts for LLM-as-judge labeling.

Rubric: TREC-style 0/1/2 graded relevance
  0 = Not relevant — the document does not address the query at all.
  1 = Partially relevant — the document touches on the topic but is incomplete,
      tangential, or only marginally useful.
  2 = Relevant — the document directly addresses the query and would genuinely
      help a user attempting to recall or learn the queried information.

The judge is asked to reason briefly, then output a single integer (0, 1, or 2)
on the final line, with no other text after it.
"""
from __future__ import annotations

_RUBRIC = """\
RELEVANCE RUBRIC
----------------
0 = Not relevant:
    The document does not address the query. It may contain some of the same
    words but is about a different topic, a different time period, or otherwise
    fails to help a user seeking the queried information.

1 = Partially relevant:
    The document touches on the query topic but is incomplete, tangential, or
    only marginally useful. A user might glance at it but would need other
    sources to fully answer their query.

2 = Relevant:
    The document directly addresses the query. A user seeking this information
    would find the document genuinely useful on its own.
"""

_EXAMPLES = """\
EXAMPLES
--------
Query: "worktree guard bypass environment variable"
Document: "Set BLACKRIM_DISABLE_WORKTREE_GUARD=1 to bypass the guard. The \
guard blocks Edit/Write outside the worktree. Use with caution."
Label: 2
Reason: The document directly answers the query — it names the exact \
environment variable and explains its effect.

---

Query: "conservative bandit budget per class"
Document: "The per-class baseline mapping is: Q1 technical-lookup → bm25, \
Q2 failure-recall → keyword+failtag, Q3 agent-scoped → bm25, Q4 continuity \
→ bm25-decay."
Label: 1
Reason: The document is related (it's about per-class retrieval policy) but \
does not explain the budget mechanism, only the baseline mapping. Partially \
relevant.

---

Query: "how to run the eval suite"
Document: "The pre-commit hook checks for unstaged changes and blocks the \
commit until they are staged or stashed."
Label: 0
Reason: The document is about pre-commit hooks, not the eval suite. Not \
relevant.
"""

_PROMPT_TEMPLATE = """\
You are a relevance assessor for an information retrieval evaluation.

{rubric}

{examples}

Now assess the following pair.

QUERY:
{query}

DOCUMENT (excerpt):
{doc_snippet}

INSTRUCTIONS:
1. Briefly reason about relevance (1–3 sentences).
2. On the very last line, output ONLY a single integer: 0, 1, or 2.
   No other text, punctuation, or explanation on that final line.

Your assessment:"""


def build_prompt(query_text: str, doc_snippet: str) -> str:
    """
    Build a graded-relevance judge prompt for a single (query, document) pair.

    Args:
        query_text:   The raw query string (or a sanitised/hashed stand-in if
                      plaintext queries are unavailable — in that case the
                      judge will produce lower-confidence labels).
        doc_snippet:  A short excerpt from the candidate document (recommended:
                      first 300 tokens / ~220 words). Truncate before calling.

    Returns:
        A fully-formed prompt string ready for the LLM judge.
    """
    return _PROMPT_TEMPLATE.format(
        rubric=_RUBRIC.strip(),
        examples=_EXAMPLES.strip(),
        query=query_text.strip(),
        doc_snippet=doc_snippet.strip(),
    )


def parse_label(response_text: str) -> int | None:
    """
    Extract the integer label from the last non-empty line of the judge response.

    Returns 0, 1, or 2 on success; None if the response is malformed.
    """
    lines = [ln.strip() for ln in response_text.strip().splitlines()]
    for line in reversed(lines):
        if not line:
            continue
        if line in ("0", "1", "2"):
            return int(line)
        # tolerate "Label: 2" or "Score: 1" as a fallback
        for token in line.split():
            if token in ("0", "1", "2"):
                return int(token)
        break  # last non-empty line was not a digit — malformed
    return None


if __name__ == "__main__":
    # Quick smoke-test of the prompt builder
    sample_prompt = build_prompt(
        query_text="worktree guard bypass environment variable",
        doc_snippet=(
            "Set BLACKRIM_DISABLE_WORKTREE_GUARD=1 to bypass the guard. "
            "The guard blocks Edit/Write outside the worktree."
        ),
    )
    print(sample_prompt)
    print()
    print("--- parse_label tests ---")
    assert parse_label("The document is relevant.\n2") == 2
    assert parse_label("Not helpful at all.\n0") == 0
    assert parse_label("Partially useful.\n1") == 1
    assert parse_label("Label: 2") == 2
    assert parse_label("nonsense") is None
    print("All parse_label assertions passed.")
