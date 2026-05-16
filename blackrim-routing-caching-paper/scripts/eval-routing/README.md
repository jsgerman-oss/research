# Routing Evaluation Harness

This directory contains the routing evaluation harness for the Blackrim
routing-caching paper.  It provides:

- **50 hand-labelled real turns** sampled from Blackrim session transcripts
- **Deterministic baseline routers** (no API calls required)
- **A CLI** (`run.py`) that scores any router and emits per-turn + summary CSVs

---

## Directory layout

```
eval-routing/
  turns/          # 50 labelled turns, one JSON file per turn
  labels.yml      # gold-standard tier labels for all 50 turns
  run.py          # CLI harness (see Usage below)
  README.md       # this file
```

---

## Turn sampling methodology

Turns were sampled from
`~/.claude/projects/-Users-jayse-Code-blackrim/*.jsonl`
(24 session files, 398 substantive user turns after filtering).

**Filtering rules applied before sampling:**

- Skip turns where `type != user` or `role != user`
- Skip sidechain turns (`isSidechain=true`) — those are subagent dispatches,
  not main-thread Gestalt prompts
- Skip turns shorter than 15 characters
- Skip turns that begin with `<task-notification>`, `<local-command`, or
  `<<autonomous-loop` (system-injected outputs, not user prompts)
- Redact secrets matching `api_key=`, `token=`, `gho_*`, `ghp_*`, `sk-*`,
  `Bearer <...>` before writing

**Stratified sample:**

| Stratum | Char length | Target | Actual |
|---------|-------------|--------|--------|
| short   | < 300       | 15     | 15     |
| medium  | 300–1500    | 20     | 20     |
| long    | > 1500      | 15     | 15     |

Turns within each stratum were drawn uniformly at random with seed 42.  The
final 50 turns were shuffled so turn number does not correlate with stratum.

Each turn file contains:

```json
{
  "id": "turn-NN",
  "session_id": "<uuid>",
  "timestamp": "<ISO-8601>",
  "user_prompt": "<text, secrets redacted>",
  "prior_context_summary": "Turn index N in session <prefix>",
  "observed_response_summary": "<first 400 chars of assistant reply>",
  "tools_used": ["Read", "Bash", ...],
  "prompt_char_length": 123
}
```

---

## Labelling rubric

Labels are stored in `labels.yml` and were assigned manually using the
rubric from
`/Users/jayse/Code/blackrim/docs/research/model-cost-quality-landscape.md`
(§ "tier boundaries").

| Tier   | When to assign |
|--------|----------------|
| haiku  | Lookup, status check, deterministic transform, slash-command parsing, single mechanical action where reasoning is NOT load-bearing |
| sonnet | Reasoning required but not novel architecture — multi-step planning, standard code edits, debugging with a known pattern, orchestration dispatch following a written spec |
| opus   | Novel design, multi-file architecture planning, high-stakes correctness (security, migrations, API contracts), ambiguous-spec interpretation |

**Conservatism rule (from RC-03 spec):** when the boundary is between sonnet
and opus, label opus.  A router that over-routes to opus is "wasteful but
correct"; under-routing to sonnet risks quality loss on load-bearing decisions.
This conservatism is intentional and is noted in the paper.

**Ambiguous turns:** if a turn genuinely cannot be classified (e.g., it
contains no semantic content, as with `[Request interrupted by user]`),
label it `ambiguous`.  Ambiguous turns are included in per-turn CSVs but
excluded from F1 calculations.

**Label distribution (50 turns):**

| Tier      | Count | % |
|-----------|-------|---|
| haiku     | 14    | 28% |
| sonnet    | 23    | 46% |
| opus      | 12    | 24% |
| ambiguous | 1     | 2%  |

The distribution is close to the RC-03 target (haiku ~20%, sonnet ~50%,
opus ~30%) but leans slightly more haiku because the real session data
contains many short slash-command invocations and one-line approvals.

---

## Usage

```bash
# From the repo root
python scripts/eval-routing/run.py \
  --router <name> \
  --turns-dir scripts/eval-routing/turns/ \
  --labels scripts/eval-routing/labels.yml \
  --out data/aggregated/routing-eval-<name>.csv
```

**Available routers:**

| Name                 | Description |
|----------------------|-------------|
| `always-opus`        | Every turn → opus.  100% recall on opus-gold; 0% recall on haiku/sonnet. |
| `always-sonnet`      | Every turn → sonnet. |
| `random-uniform`     | Uniform random over {haiku, sonnet, opus}.  Expected accuracy ≈ 33%. |
| `length-heuristic`   | <300 chars → haiku, 300–1500 → sonnet, >1500 → opus. |
| `semantic-similarity`| Stub only (returns haiku for all turns).  RC-04 replaces the body. |

**Output files produced:**

- `data/aggregated/routing-eval-<router>.csv` — 50-row per-turn results
- `data/aggregated/routing-summary-<router>.csv` — per-tier precision/recall/F1
- `data/aggregated/routing-baseline-results.csv` — one row per router run (appended)

**Per-turn CSV schema:**

| Column                  | Description |
|-------------------------|-------------|
| `turn_id`               | e.g. `turn-01` |
| `gold_tier`             | Ground-truth label from `labels.yml` |
| `pred_tier`             | Predicted tier from the router |
| `correct`               | 1 if gold == pred (and gold != ambiguous), else 0 |
| `cost_saved_vs_opus_usd`| USD saved vs always-opus for this turn (negative = more expensive than opus) |
| `cost_of_mistake_usd`   | USD proxy for quality risk when under-routing (pred cheaper than gold) |

Cost calculations use 500-token average prompt length and these illustrative
prices (per million input tokens): haiku $0.25, sonnet $3.00, opus $15.00.

---

## Baseline results (dry-run, 49 turns excluding 1 ambiguous)

| Router           | Accuracy | Macro-F1 | Haiku F1 | Sonnet F1 | Opus F1 | Cost saved vs opus |
|------------------|----------|----------|----------|-----------|---------|-------------------|
| always-opus      | 24.5%    | 0.131    | 0.000    | 0.000     | 0.393   | $0.000000 |
| random-uniform   | 20.4%    | 0.191    | 0.148    | 0.286     | 0.138   | $0.000210 |
| length-heuristic | 51.0%    | 0.466    | 0.357    | 0.744     | 0.296   | $0.000223 |

`always-opus` achieves 100% recall on opus-gold turns and 0% on haiku/sonnet
as expected.  `random-uniform` lands near 20% (expected ~33%; variance at N=50
with seed=0 accounts for the gap).  `length-heuristic` is the strongest
baseline at 51% accuracy, mainly due to reasonable sonnet F1 (0.744).

---

## Semantic-similarity router (RC-04)

The `semantic-similarity` router is a k-nearest-neighbour classifier over
sentence embeddings.  It is the headline router described in §7 of the paper.

### How it works

1. At construction, each exemplar in `labels.yml` (excluding `ambiguous` turns
   and, in LOO-CV mode, the held-out turn) is encoded with a
   sentence-transformers model by concatenating `user_prompt` and
   `observed_response_summary`.
2. At routing time the query turn is encoded the same way, cosine similarity is
   computed against all exemplar embeddings (L2-normalised dot product), and the
   majority-vote tier of the top-`k` neighbours (`k=5` default) is returned.
3. **Conservative escalation**: if the maximum cosine similarity to any
   exemplar is below `min_similarity` (default `0.30`), the router returns
   `opus` unconditionally — treating the turn as out-of-distribution and
   preferring the safest, most capable tier.

The implementation lives in `routers/semantic_similarity.py`.
`run.py` imports it through the `routers/` package (added to `sys.path` at
load time, so it works regardless of the caller's working directory).

### Dependency

```bash
pip install sentence-transformers
```

The default model is `all-MiniLM-L6-v2` (~80 MB download on first use, CPU-only,
no GPU required).

### Swapping models

Set the `SEMANTIC_ROUTER_MODEL` environment variable to any
[sentence-transformers model identifier](https://www.sbert.net/docs/pretrained_models.html)
before running:

```bash
SEMANTIC_ROUTER_MODEL=paraphrase-multilingual-MiniLM-L12-v2 \
  python scripts/eval-routing/run.py --router semantic-similarity --cv-loo \
  --turns-dir scripts/eval-routing/turns/ \
  --labels scripts/eval-routing/labels.yml \
  --out data/aggregated/routing-eval-semantic-multilingual.csv
```

Or pass `model_name` when constructing `SemanticSimilarityRouter` directly.

### Leave-one-out cross-validation

Use `--cv-loo` to run LOO-CV (only supported for `semantic-similarity`):

```bash
python scripts/eval-routing/run.py \
  --router semantic-similarity \
  --cv-loo \
  --turns-dir scripts/eval-routing/turns/ \
  --labels scripts/eval-routing/labels.yml \
  --out data/aggregated/routing-eval-semantic.csv
```

Each of the 50 turns is evaluated with that turn excluded from the exemplar
set, producing an unbiased generalisation estimate.  The run takes roughly
60–90 seconds on a modern laptop CPU (50 model re-instantiations × ~50
exemplar encodings each, with cached model weights).

### Results (LOO-CV, N=49 non-ambiguous turns)

| Router                   | Accuracy | Macro-F1 | Haiku F1 | Sonnet F1 | Opus F1 | Cost saved vs opus |
|--------------------------|----------|----------|----------|-----------|---------|--------------------|
| always-opus              | 24.5%    | 0.131    | 0.000    | 0.000     | 0.393   | $0.000000 |
| random-uniform           | 20.4%    | 0.191    | 0.148    | 0.286     | 0.138   | $0.000210 |
| length-heuristic         | 51.0%    | 0.466    | 0.357    | 0.744     | 0.296   | $0.000223 |
| **semantic-similarity**  | **61.2%**| **0.526**| **0.786**| **0.667** | 0.125   | **$0.000289** |

The semantic router's main weakness is opus recall (F1 0.125): short,
design-pivoting opus turns are superficially similar to routine sonnet queries
and the 53-exemplar set lacks sufficient opus prototype coverage.

---

## Adding a new router

1. Subclass `Router` in `run.py`:

   ```python
   class MyRouter(Router):
       name = "my-router"

       def route(self, turn: dict) -> str:
           # turn["user_prompt"]       — full prompt text
           # turn["prompt_char_length"] — char count
           # turn["tools_used"]         — list of tool names from the response
           return "sonnet"  # return "haiku", "sonnet", or "opus"
   ```

2. Register it in the `ROUTERS` dict near the top of `run.py`:

   ```python
   ROUTERS: dict[str, type[Router]] = {
       ...
       "my-router": MyRouter,
   }
   ```

3. Run it:

   ```bash
   python scripts/eval-routing/run.py --router my-router \
     --turns-dir scripts/eval-routing/turns/ \
     --labels scripts/eval-routing/labels.yml \
     --out data/aggregated/routing-eval-my-router.csv
   ```

4. The new router's summary row is appended to
   `data/aggregated/routing-baseline-results.csv` automatically.
