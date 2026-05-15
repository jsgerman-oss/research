#!/usr/bin/env python3
"""
refactor-eval.py — STUB. Backs §6.6 (OQ-AST-4).

Once OQ-AST-4 is unblocked (a curated 200-diff corpus exists), this
script will:

  1. Read a YAML-described corpus of (intent, file, expected_verdict)
     triples from scripts/refactor-corpus.yaml. Intents:
     rename-symbol, extract-to-package, fix-imports.
  2. For each triple, run `gt <intent> <file>` to obtain the plan +
     candidate diff, then submit to the compile gate.
  3. Compare the gate verdict to expected_verdict (ground-truth review).
  4. Emit CSV with the confusion matrix per intent per language:
     intent, lang, n_tested, true_pos, false_pos, true_neg, false_neg.

False positives must be zero (the false-negative-only contract,
Def. 3.2 in the paper). False negatives must be ≤ 5% (the conservatism
budget, §6.6).

Emitting a header-only CSV now keeps the LaTeX build green during
draft revisions; replace with the real implementation when the corpus
is curated.
"""
from __future__ import annotations

import csv
import sys


def main() -> int:
    w = csv.writer(sys.stdout)
    w.writerow(["intent", "lang", "n_tested",
                "true_pos", "false_pos", "true_neg", "false_neg",
                "false_pos_rate", "false_neg_rate"])
    # No rows yet — OQ-AST-4 dataset is pending.
    return 0


if __name__ == "__main__":
    sys.exit(main())
