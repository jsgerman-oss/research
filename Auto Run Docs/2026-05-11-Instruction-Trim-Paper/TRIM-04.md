# TRIM-04 — Fidelity eval: live execution + §6 update

## Goal
Run the harness shipped in TRIM-03 against the **real** Anthropic API,
produce `fidelity-baseline.csv` and `fidelity-wave2.csv`, compute the
Δ-score, and replace the `\tothink` qualitative-check paragraph in §6
with measured numbers. This is the phase that makes the paper's
quality-preservation claim a measured one rather than asserted.

## Context — what to read first
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- TRIM-03 must be complete. `scripts/eval-fidelity/run.py` must work
  in `--dry-run` mode.
- §6 "Fidelity check" subsection: `sections/06-evaluation.tex`
  lines 52-65 (the `\tothink` block + the cache-cost analysis
  cite the "all post-trim agents completed successfully" qualitative
  argument that this phase replaces).
- API key: the operator must have `ANTHROPIC_API_KEY` set in the
  environment before launching this phase. If unset, STOP and tell
  the operator — do not run a partial measurement.

## Budget + safety
- Expected cost: ~20 prompts × 2 prefix versions × ~2k input + 1k
  output tokens × Opus pricing ≈ **$5-8 USD** for the full run.
  Refuse to proceed if `--prompts` has >40 entries (likely an
  expansion that wasn't budgeted for).
- Add a `--max-cost-usd 10` safety flag in `scripts/eval-fidelity/run.py`
  that aborts mid-run if cumulative cost exceeds the cap.

## Tasks
- [ ] Verify `ANTHROPIC_API_KEY` is set:
  `[ -n "$ANTHROPIC_API_KEY" ] || (echo "set ANTHROPIC_API_KEY first"; exit 1)`.
  If unset, STOP. Do not synthesize a key, do not stub the calls.
- [ ] Add the `--max-cost-usd` safety flag to
  `scripts/eval-fidelity/run.py` if not already present.
- [ ] Run baseline:
  `python scripts/eval-fidelity/run.py
   --prefix-sha <baseline-sha-from-trim-results.csv>
   --prompts scripts/eval-fidelity/prompts.yml
   --out data/aggregated/fidelity-baseline.csv
   --max-cost-usd 10`. Verify the CSV has one row per prompt and the
  `score` column has real fractions (not all 0 or 1).
- [ ] Run Wave-2:
  `python scripts/eval-fidelity/run.py
   --prefix-sha <wave2-sha-from-trim-results.csv>
   --prompts scripts/eval-fidelity/prompts.yml
   --out data/aggregated/fidelity-wave2.csv
   --max-cost-usd 10`.
- [ ] Create `scripts/aggregate-fidelity-delta.py` that reads both
  CSVs and emits `data/aggregated/fidelity-delta.csv` with columns:
  `dimension, baseline_score, wave2_score, delta, n_prompts`. One row
  per dimension + one `OVERALL` row.
- [ ] Rewrite §6 "Fidelity check" subsection
  (`sections/06-evaluation.tex` lines 52-65). Drop the `\tothink`.
  New prose structure: (1) one paragraph describing the eval suite
  (cite TRIM-03 prompts.yml — N prompts, 4 dimensions), (2) a small
  table `\label{tab:fidelity-delta}` showing baseline / wave2 /
  Δ per dimension + overall, (3) one paragraph interpreting the
  result: if Δ within ε (define ε=0.05), claim fidelity-preservation;
  if larger, report honestly and treat as a limitation in §7.
- [ ] If overall Δ > ε, also update the abstract (§0) and the
  introduction (§1) contribution claim — the paper currently
  promises "without instruction-fidelity loss"; if measurement
  disagrees, the claim must be softened to match measurement, not
  vice versa. (This is non-negotiable. Do not fudge the eval to
  preserve the claim.)
- [ ] Commit (data first, then prose): `eval(trim): live fidelity
  eval run — baseline vs wave2 Δ measured` with the per-dimension
  delta numbers in the commit body.

## Acceptance criteria
- `data/aggregated/fidelity-baseline.csv` and `fidelity-wave2.csv`
  exist with real responses (not "DRY_RUN").
- `data/aggregated/fidelity-delta.csv` exists.
- §6 has the new table + interpretive paragraph; no `\tothink` left
  in the fidelity-check subsection.
- If Δ exceeded ε, §0 + §1 + §7 reflect that honestly.

## Failure modes — escalate, don't paper over
- API errors: report and stop. Don't retry indefinitely (rate-limit
  the harness to ~5 req/min).
- Rubric scoring near-zero for both: the harness is broken, not the
  trim. Re-check `rubric.py` regex patterns before re-running.
- Wave-2 score MUCH lower than baseline: real degradation; report
  honestly per the §0/§1/§7 update rule above.

## Out of scope
- LLM-as-judge scoring.
- Cross-model comparison.
- Statistical significance testing (n is too small; report Δ +
  per-dimension n only).
