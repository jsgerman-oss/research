# TRIM-03 — Held-out fidelity eval suite: design + harness

## Goal
Build the **instruction-following eval harness** that §6's "Fidelity check"
subsection currently leaves as a `\tothink`. This phase ships the
harness (prompts + scorer + CLI) without running it against the live
Claude Code API — that's TRIM-04. The harness must be deterministic enough
to be re-runnable as a regression gate.

## Context — what to read first
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- §6 fidelity check currently lives at `sections/06-evaluation.tex` around
  lines 52-65 (the `\tothink` block).
- The four "instruction-following dimensions" the trim risks degrading
  (read these from §6 and §5): worktree isolation, delegation discipline,
  commit path, merge flow.
- The pre-trim and post-trim CLAUDE.md are accessible at the SHAs
  recorded in `data/aggregated/trim-results.csv` (TRIM-01 output).

## Tasks
- [ ] Create `scripts/eval-fidelity/` directory. Inside, create
  `prompts.yml` — a YAML list of 12-20 eval prompts. Each entry is a
  dict with keys: `id` (e.g. `worktree-01`), `dimension` (one of
  `worktree-isolation | delegation | commit-path | merge-flow`),
  `prompt` (the user message — a realistic Blackrim-style task that
  SHOULD invoke the rule, e.g. "Make a change in the worktree at
  /tmp/foo and commit it"), `rubric` (a list of checks the response
  must satisfy: e.g. `must_mention_main_worktree_path`,
  `must_not_run_git_commit_in_worktree`). 3-5 prompts per dimension.
- [ ] Create `scripts/eval-fidelity/rubric.py` — pure-Python scorer.
  Each rubric check is a function `check_<name>(response_text: str,
  context: dict) -> bool`. Implement only string-matching / regex
  checks; no LLM-as-judge. Failing to score a prompt = `unscored`,
  not `fail`. Keep this small (<200 lines).
- [ ] Create `scripts/eval-fidelity/run.py` — the CLI. Accepts:
  `--prefix-sha <SHA>` (which CLAUDE.md version to test against,
  pulled via `git -C /Users/jayse/Code/blackrim show`),
  `--prompts scripts/eval-fidelity/prompts.yml`,
  `--out data/aggregated/fidelity-<sha>.csv`,
  `--dry-run` (skip API calls; useful for harness CI).
  In `--dry-run`, write a CSV with synthetic responses (the literal
  string "DRY_RUN") so the rubric runs and the schema validates.
  Real-call mode uses the Anthropic SDK with the CLAUDE.md content
  loaded as a system message; one call per prompt; model =
  `claude-opus-4-7` (the model under measurement).
- [ ] Output CSV schema: `prompt_id, dimension, prefix_sha,
  response_chars, <each-rubric-check>, score, notes`. The `score`
  is the fraction of applicable rubric checks that pass.
- [ ] Smoke-test the harness end-to-end in dry-run:
  `python scripts/eval-fidelity/run.py --prefix-sha <baseline-sha>
  --prompts scripts/eval-fidelity/prompts.yml --dry-run
  --out data/aggregated/fidelity-baseline-dryrun.csv`. Verify the CSV
  has one row per prompt and the rubric ran (most checks will fail
  against "DRY_RUN" string — that's correct behavior).
- [ ] Add a `make fidelity-dryrun` target to the Makefile that runs
  the dry-run end-to-end against both pre-trim and post-trim SHAs.
- [ ] Document the harness in `scripts/eval-fidelity/README.md`:
  what each dimension probes, how to add new prompts, how the
  scorer works, how to interpret the output CSV, what the API-cost
  budget is for a full live run (~20 prompts × 2 prefix versions ×
  Opus pricing).
- [ ] Commit: `eval(trim): fidelity eval harness — prompts, rubric,
  dry-run CLI (no live API yet)`.

## Acceptance criteria
- `scripts/eval-fidelity/{prompts.yml,rubric.py,run.py,README.md}`
  all exist.
- `python scripts/eval-fidelity/run.py --dry-run` exits 0 and
  produces a valid CSV.
- `make fidelity-dryrun` runs clean.
- §6 and the paper itself are not modified yet — that's TRIM-04.

## Out of scope
- Live API execution (TRIM-04).
- LLM-as-judge scoring (deferred to future work; flag in §8).
- Cross-model comparison (this paper only measures
  `claude-opus-4-7`).
