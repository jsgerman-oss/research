#!/usr/bin/env python3
"""
e2e-paired-traces.py — STUB. Backs §6.7 (OQ-AST-5).

This is the central pending claim for the paper. Once OQ-AST-5 is
unblocked, this script will:

  1. Load a paired-trace dataset: N_task ≥ 50 Explore-tier tasks, each
     run twice — once with outline-discipline enabled, once with it
     disabled — same agent, same task, same prompt, same model tier.
  2. Join the two runs by task_id; compute per-task deltas:
     - input_tokens_delta (with - without; negative = savings)
     - wall_clock_delta_seconds
     - success_delta ({-1, 0, +1})
  3. Bootstrap 95% CIs over per-task deltas with 1000 resamples.
  4. Emit CSV: task_id, agent, with_tokens, without_tokens,
     tokens_delta, with_wall_s, without_wall_s, wall_delta_s,
     with_success, without_success, success_delta.

The §6.7 figure plots the per-task tokens_delta distribution (boxplot
or violin) and reports the mean + bootstrap CI. Headline claim
candidate (pending data): ≥50% input-token reduction at p_50 with no
measurable success regression.

Emitting a header-only CSV now keeps the LaTeX build green; replace
with the real implementation when the paired-trace dataset accumulates.
"""
from __future__ import annotations

import csv
import sys


def main() -> int:
    w = csv.writer(sys.stdout)
    w.writerow(["task_id", "agent",
                "with_tokens", "without_tokens", "tokens_delta",
                "with_wall_s", "without_wall_s", "wall_delta_s",
                "with_success", "without_success", "success_delta"])
    # No rows yet — OQ-AST-5 dataset is pending.
    return 0


if __name__ == "__main__":
    sys.exit(main())
