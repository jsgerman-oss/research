#!/usr/bin/env python3
"""Aggregate per-section residency data from CLAUDE.md at baseline, Wave 1, and Wave 2 SHAs.

Reads the Blackrim git history to count lines per top-level (##-level) section at
three trim snapshots.  Emits a CSV with one row per baseline section.

The `classification` and `externalised_to` columns are pre-populated with
hand-applied labels per the §5 taxonomy:
  must-resident     — every spawn semantically needs this section
  frequency-deciding — read-mostly or large; algorithm decides keep vs externalise
  redundant         — duplicated within prefix or against an existing external doc

Usage:
    python scripts/aggregate-section-residency.py \\
        --repo /Users/jayse/Code/blackrim \\
        --baseline-sha 6414995 \\
        --wave1-sha    55ff9e9 \\
        --wave2-sha    6c7f3a0 \\
        > data/aggregated/section-residency.csv

The SHAs can be found in data/aggregated/trim-results.csv (row 1 = baseline,
first negative-delta row for Wave 1, next large-delta row for Wave 2).
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Hand-applied classification table (§5 taxonomy).
# Keys are the ## heading text (verbatim, minus the "## " prefix).
# Values: (classification, externalised_to)
#   - classification: must-resident | frequency-deciding | redundant
#   - externalised_to: canonical external path, or "" if kept resident
#
# These labels reflect the Wave-2 outcome — sections that shrank to near-zero
# were externalised; sections fully kept are must-resident or frequency-deciding
# but above the f·r < 0.235·|s| threshold.
# ---------------------------------------------------------------------------
CLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "How It Works": (
        "must-resident",
        "",
    ),
    "Delegation discipline": (
        "must-resident",
        "",
    ),
    "Skill-Driven Workflow": (
        "frequency-deciding",
        "",
    ),
    "Background Agents (Gestalt spawning citizens/workers)": (
        "frequency-deciding",
        "",
    ),
    "Human-in-the-Loop Approval (Subagent Tool Denials)": (
        "must-resident",
        "",
    ),
    "Beads Issue Tracker": (
        "must-resident",
        "",
    ),
    "Session Completion": (
        "must-resident",
        "",
    ),
    "Agent System (8 citizens + 7 exoselves, Polis frame)": (
        "redundant",
        "agents/citizens/, agents/workers/",
    ),
    "Customization": (
        "redundant",
        "mkdocs/operations/customization.md",
    ),
}

# Within "Background Agents", the "Worktree isolation" subsection is the
# headline example cited in §5.  It is tracked separately in the script
# output comment but not as a separate CSV row (the CSV is ## granularity).
WORKTREE_ISOLATION_NOTE = (
    "Worktree isolation (###-level subsection of Background Agents): "
    "76 lines at baseline/Wave-1 -> 14 lines at Wave 2 (82% reduction). "
    "Externalised to mkdocs/operations/worktree-guard.md."
)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    )


def get_claude_md(repo: Path, sha: str) -> str:
    """Return full CLAUDE.md content at the given SHA."""
    try:
        return git(repo, "show", f"{sha}:CLAUDE.md")
    except subprocess.CalledProcessError:
        print(f"WARNING: could not read CLAUDE.md at {sha}", file=sys.stderr)
        return ""


def parse_sections(content: str) -> dict[str, int]:
    """Return {section_title: line_count} for every ##-level heading.

    The section body includes lines from the ## heading down to (but not
    including) the next ## heading.  Sub-headings (###, ####, etc.) are
    counted as part of the enclosing ##-section.
    """
    sections: dict[str, int] = {}
    current: str | None = None
    count = 0

    for line in content.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = count
            current = line[3:].strip()
            count = 1  # count the heading line itself
        elif current is not None:
            count += 1

    if current is not None:
        sections[current] = count

    return sections


def round1(x: float) -> str:
    return f"{x:.1f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default="/Users/jayse/Code/blackrim", type=Path)
    ap.add_argument(
        "--baseline-sha",
        default="6414995",
        help="SHA of the pre-trim baseline commit (row 1 of trim-results.csv)",
    )
    ap.add_argument(
        "--wave1-sha",
        default="55ff9e9",
        help="SHA of the first Wave-1 trim commit",
    )
    ap.add_argument(
        "--wave2-sha",
        default="6c7f3a0",
        help="SHA of the Wave-2 trim commit",
    )
    args = ap.parse_args()

    if not args.repo.exists():
        print(f"ERROR: repo not found: {args.repo}", file=sys.stderr)
        sys.exit(2)

    baseline_content = get_claude_md(args.repo, args.baseline_sha)
    wave1_content = get_claude_md(args.repo, args.wave1_sha)
    wave2_content = get_claude_md(args.repo, args.wave2_sha)

    if not baseline_content:
        print("ERROR: baseline CLAUDE.md is empty; cannot proceed.", file=sys.stderr)
        sys.exit(1)

    baseline_sections = parse_sections(baseline_content)
    wave1_sections = parse_sections(wave1_content)
    wave2_sections = parse_sections(wave2_content)

    # Validate classifications cover all baseline sections
    unknown = set(baseline_sections) - set(CLASSIFICATIONS)
    if unknown:
        print(
            f"WARNING: {len(unknown)} baseline section(s) lack hand-applied "
            f"classification -- they will be tagged TODO:\n  "
            + "\n  ".join(sorted(unknown)),
            file=sys.stderr,
        )

    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "section_title",
            "baseline_lines",
            "wave1_lines",
            "wave2_lines",
            "delta_lines",
            "delta_pct",
            "classification",
            "externalised_to",
        ]
    )

    # Emit one row per baseline section, in document order
    seen_in_order: list[str] = []
    for line in baseline_content.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            if title not in seen_in_order:
                seen_in_order.append(title)

    for title in seen_in_order:
        bl = baseline_sections.get(title, 0)
        w1 = wave1_sections.get(title, 0)
        w2 = wave2_sections.get(title, 0)
        delta = w2 - bl
        pct = (delta / bl * 100.0) if bl else 0.0

        cls, ext = CLASSIFICATIONS.get(title, ("TODO", ""))

        writer.writerow(
            [
                title,
                bl,
                w1,
                w2,
                delta,
                round1(pct),
                cls,
                ext,
            ]
        )

    print(
        f"# NOTE: {WORKTREE_ISOLATION_NOTE}",
        file=sys.stderr,
    )
    print(
        "# Run with: python scripts/aggregate-section-residency.py"
        " --repo /Users/jayse/Code/blackrim"
        " --baseline-sha 6414995"
        " --wave1-sha 55ff9e9"
        " --wave2-sha 6c7f3a0"
        " > data/aggregated/section-residency.csv",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
