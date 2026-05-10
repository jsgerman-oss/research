# Per-Turn Model Routing and Agentic Plan Caching for Cost-Optimal Multi-Agent LLM Coding Systems

Source for the research paper introducing two complementary cost-optimization primitives for static-prefix multi-agent LLM coding systems:

1. **Per-turn model routing** — a semantic-similarity classifier that routes each main-thread orchestration turn to the cost-minimal model tier (haiku / sonnet / opus) preserving instruction-following quality. Estimated 35–50% main-thread cost reduction at <1% quality loss, based on landscape research grounded in FrugalGPT (arXiv 2305.05176), RouteLLM (arXiv 2406.18665), Tryage (arXiv 2308.11601), and confidence-based routing literature (arXiv 2410.13284v3).

2. **Agentic plan caching** — a semantic plan-level cache complementary to existing prefix caching. Per NeurIPS 2025 *Agentic Plan Caching*, achieves 50% additional cost reduction and 27% latency improvement on top of an already-69%-efficient prefix-cache baseline.

The paper is grounded in empirical telemetry from \blackrim's production sessions: a measured 99.4% main-thread / 0.6% dispatch cost split, 4.56× cache read-to-creation ratio, and the cost-quality frontier across haiku-4-5, sonnet-4-6, opus-4-7.

## Build

```bash
brew install --cask basictex          # ~100 MB
# or use Overleaf (upload main.tex + sections/ + bib/)

make            # build main.pdf
make watch      # rebuild on change
make view       # open PDF
make data       # rebuild data/aggregated/*.csv from data/raw/*.json
make clean      # remove build artifacts
make wordcount  # texcount per section
```

## Layout

```
.
├── main.tex                    # master — \input's section files
├── Makefile
├── README.md
├── .gitignore
├── sections/
│   ├── 00-abstract.tex
│   ├── 01-introduction.tex
│   ├── 02-related-work.tex
│   ├── 03-problem-formulation.tex
│   ├── 04-system.tex
│   ├── 05-routing-algorithm.tex
│   ├── 06-plancache-algorithm.tex
│   ├── 07-evaluation.tex
│   ├── 08-discussion.tex
│   ├── 09-future-work.tex
│   ├── 10-conclusion.tex
│   └── A-appendix.tex
├── bib/refs.bib
├── figures/
├── data/
│   ├── raw/                    # session telemetry: 2026-05-09 routing+caching findings
│   └── aggregated/             # CSVs backing §7 figures/tables
└── scripts/                    # reproducibility — pull-telemetry.py + aggregators
```

## Reproducibility

Every quantitative claim in §7 (Empirical Evaluation) traces back to a CSV in `data/aggregated/` produced by a script in `scripts/`. To reproduce:

```bash
python scripts/pull-telemetry.py --since 2026-05-01 \
  --repo /Users/jayse/Code/blackrim \
  > data/raw/session-telemetry.json

python scripts/aggregate-routing-evidence.py \
  < data/raw/session-telemetry.json \
  > data/aggregated/routing-evidence.csv

python scripts/aggregate-cache-stats.py \
  --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl \
  > data/aggregated/cache-stats.csv

make
```

## Companion software + research

This paper synthesises:

- **`docs/research/tier-down-main-thread-landscape.md`** (commit `ecfdcba` on Blackrim main) — the Phase A landscape research, 7,500+ words, ~30 arxiv citations.
- **`docs/research/cache-control-deep-dive.md`** (commit `660054d`) — empirical cache-pattern analysis + plan-caching opportunity.
- **`docs/research/multi-agent-optimization-landscape.md`** (commit `aa9ddba`) — the 9,000-word top-10-ranked optimization survey that flagged routing + caching as priorities #1–#3.
- **`internal/dispatch/model.go`** (Blackrim) — the existing 16-rule cascade for SUBAGENT routing (`blackrim-9w29` MOA-3, commit by `blackrim-fasf`); main-thread routing is the natural extension.
- **`docs/research/model-cost-quality-landscape.md`** (commit `59d333d`, MOA-1, `blackrim-x4u1`) — the empirical cost-quality matrix across roles × tiers; transferable cost-frontier data.

Companion paper: `~/research/blackrim-instruction-trim-paper/` (the static-prefix trim methodology — 17.1% reduction on \claudemd) is a sibling contribution.

## Status

Draft skeleton (this commit). Section content is placeholder-with-substantive-where-data-exists; flesh out before submission. Targeting arxiv preprint as the first venue; routing-and-caching workshops at NeurIPS / MLSys / ICLR 2026 under consideration.

## License

CC BY 4.0 for the paper text and figures (TODO: add `LICENSE` file at submission time).
