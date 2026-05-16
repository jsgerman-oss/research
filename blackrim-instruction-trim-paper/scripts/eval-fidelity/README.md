# eval-fidelity — TRIM-03 Fidelity Evaluation Harness

This directory contains the held-out instruction-following eval described in
§6 of the instruction-trim paper. The harness measures whether a trimmed
`CLAUDE.md` still produces agent behavior equivalent to the baseline on four
behavioral dimensions.

## Files

| File | Purpose |
|------|---------|
| `prompts.yml` | 16 eval prompts, 4 per dimension |
| `rubric.py` | Pure-Python string-match scorer |
| `run.py` | CLI — dry-run and live-API eval runner |

---

## Dimensions

### `worktree-isolation`
Probes whether the model correctly mandates `isolation: "worktree"` on every
agent spawn. The trimmed CLAUDE.md externalised the deep-dive prose about
this requirement to `mkdocs/operations/worktree-guard.md` while keeping the
canonical rule in the system prompt. These prompts verify the rule still fires.

**Key substrings checked:** `isolation`, `worktree`
**Forbidden:** `isolation: false`, responses that dismiss the requirement as optional.

### `delegation`
Probes whether the model routes work to the right worker (Researcher, Builder,
Writer) rather than doing it inline. The delegation table in CLAUDE.md defines
clear thresholds; these prompts verify the thresholds are honored.

**Key substrings checked:** `Researcher`, `Builder`, `Writer`, `transform`
**Forbidden:** responses that encourage self-doing above the threshold.

### `commit-path`
Probes whether the model directs all commits through `gt commit` rather than
raw `git commit -m`. CLAUDE.md is explicit that there is no fallback.

**Key substrings checked:** `gt commit`
**Forbidden:** `git commit -m`, `git commit --message`

### `merge-flow`
Probes whether the model directs agent-branch merges through
`bin/blackrim-merge-agent` (or `gt orchestrate merge-and-report`) and
explicitly warns against `git cherry-pick`.

**Key substrings checked:** `bin/blackrim-merge-agent`
**Forbidden:** `cherry-pick`, responses that treat cherry-pick as equivalent.

---

## How to add a new prompt

1. Open `prompts.yml`.
2. Append a new entry under `prompts:` with these fields:

```yaml
- id: <dimension>-<NN>          # e.g. worktree-05
  dimension: <dimension>        # worktree-isolation | delegation | commit-path | merge-flow
  prompt: >
    <The user-facing task message. Write it as a realistic Blackrim operator
    would phrase it — ask for an action, not a definition.>
  expected_substrings:
    - "substring that MUST appear"
  forbidden_substrings:
    - "substring that must NOT appear"
```

3. Run the dry-run to confirm the schema parses:
   ```
   make fidelity-dryrun
   ```
4. Inspect the CSV — the new row's `status` will be `fail` in dry-run
   (expected; the literal `DRY_RUN` response won't contain your substrings).

---

## Extracting a CLAUDE.md snapshot from a Blackrim commit

```bash
git -C /path/to/blackrim show <SHA>:CLAUDE.md > snapshot.md
```

The baseline and Wave-2 SHAs are recorded in
`data/aggregated/trim-results.csv` (columns `sha` and `subject`).

Example:
```bash
git -C /Users/jayse/Code/blackrim show eb8c3d0:CLAUDE.md > /tmp/baseline.md
git -C /Users/jayse/Code/blackrim show 6c7f3a0:CLAUDE.md > /tmp/wave2.md
```

---

## Running

### Dry-run (no API key required)

```bash
# From the paper root:
python scripts/eval-fidelity/run.py \
    --prefix-sha eb8c3d0 \
    --prompts scripts/eval-fidelity/prompts.yml \
    --dry-run \
    --out data/aggregated/fidelity-baseline-dryrun.csv
```

Or using a local file as the prefix:
```bash
python scripts/eval-fidelity/run.py \
    --prefix /tmp/baseline.md \
    --dry-run \
    --out data/aggregated/fidelity-dryrun-sample.csv
```

Or via make:
```bash
make fidelity-dryrun
```

### Live run (requires ANTHROPIC_API_KEY)

```bash
export ANTHROPIC_API_KEY=sk-ant-...

python scripts/eval-fidelity/run.py \
    --prefix-sha eb8c3d0 \
    --prompts scripts/eval-fidelity/prompts.yml \
    --model claude-opus-4-7 \
    --cost-budget-usd 2.0 \
    --out data/aggregated/fidelity-eb8c3d0.csv
```

The `--cost-budget-usd` flag is a hard cap. The script estimates the run
cost before making any API calls and exits non-zero if the estimate exceeds
the budget.

---

## Output CSV schema

| Column | Type | Description |
|--------|------|-------------|
| `prompt_id` | str | From prompts.yml (`worktree-01`, etc.) |
| `dimension` | str | `worktree-isolation` \| `delegation` \| `commit-path` \| `merge-flow` |
| `prefix_sha` | str | SHA or file stem used as the system-prompt prefix |
| `response_chars` | int | Length of model response in characters |
| `hit_expected` | int | Number of expected substrings found |
| `total_expected` | int | Total expected substrings |
| `hit_forbidden` | int | Number of forbidden substrings found |
| `total_forbidden` | int | Total forbidden substrings |
| `score` | float | `hit_expected / total_expected` (0.0 if any forbidden matched) |
| `status` | str | `pass` \| `fail` \| `unscored` |
| `notes` | str | Missing / found substrings for debugging |

---

## Interpreting results

- **pass rate** — fraction of prompts with `status=pass`. Target: ≥ 0.85 for
  a trimmed version to be considered fidelity-preserving.
- **avg score** — mean of per-prompt `score` values. Useful for tracking
  partial-credit degradation across waves.
- **fail on dry-run** — expected and correct. The rubric running against
  `DRY_RUN` responses validates the harness schema, not the model behavior.

---

## API cost budget

A full live run (16 prompts × 2 prefix versions — baseline + Wave 2):

| Item | Estimate |
|------|---------|
| Prefix tokens per call (cache-read after first) | ~12,000 tokens |
| Input per prompt | ~50 tokens |
| Output per prompt | ~400 tokens |
| Total calls | 32 |
| Estimated cost | < $0.50 USD |

The `--cost-budget-usd 2.0` default is conservative. Adjust down for smaller
models or fewer prompts.

---

## Dependencies

- Python 3.9+
- `pyyaml` (standard in most envs; `pip install pyyaml` if missing)
- `anthropic` — required only for live runs (`pip install anthropic`)
