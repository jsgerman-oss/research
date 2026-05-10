# Frequency-Weighted Progressive Disclosure for Static-Prefix Multi-Agent Coding Systems

Source for the research paper introducing a **measurement-first methodology** for trimming static instruction documents (CLAUDE.md and equivalents) loaded into every agent spawn in multi-agent LLM coding systems. Contribution: a **frequency-weighted residency model** that decides what stays in-prefix vs. externalizes to on-demand Read calls; applied to Blackrim and measured at 21.5% line reduction without instruction-fidelity loss.

## Build

LaTeX toolchain required (any of):

```bash
brew install --cask basictex          # ~100 MB
brew install --cask mactex-no-gui     # ~5 GB
# or use Overleaf (upload main.tex + sections/ + bib/)
```

Then:

```bash
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
├── Makefile                    # latexmk + lint + wordcount targets
├── README.md
├── .gitignore
├── sections/
│   ├── 00-abstract.tex
│   ├── 01-introduction.tex
│   ├── 02-related-work.tex
│   ├── 03-problem-formulation.tex
│   ├── 04-system.tex
│   ├── 05-algorithm.tex
│   ├── 06-evaluation.tex
│   ├── 07-discussion.tex
│   ├── 08-future-work.tex
│   ├── 09-conclusion.tex
│   └── A-appendix.tex
├── bib/refs.bib                # BibTeX bibliography
├── figures/                    # TikZ + pgfplots sources
├── data/
│   ├── raw/                    # session telemetry (commits, bd lifecycle, sizes)
│   └── aggregated/             # CSV result files backing §6 figures/tables
└── scripts/                    # eval harness — reproduces data/ from raw telemetry
```

## Reproducibility

Every quantitative claim in §6 (Empirical Evaluation) is backed by a CSV in `data/aggregated/` produced by a script in `scripts/`. To reproduce from scratch:

```bash
python scripts/pull-telemetry.py --since 2026-05-09 > data/raw/session-telemetry.json
python scripts/aggregate-trim-results.py < data/raw/session-telemetry.json > data/aggregated/trim-results.csv
make            # latex picks up new data/*.csv automatically
```

## Companion software + data

- The methodology was applied to [Blackrim](https://github.com/jsgerman-oss/blackrim.dev) (commit `6c7f3a0`).
- The optimization landscape that motivated several "future work" entries lives at `docs/research/multi-agent-optimization-landscape.md` in the Blackrim repo.
- Cache-control marker investigation (negative result, blocked on Anthropic / Claude Code feature support): `docs/research/cache-control-markers.md`.

## Status

Draft skeleton (this commit). Section content is placeholder-with-substantive-where-data-exists; flesh out before submission. Targeting arxiv preprint as the first venue; workshop submissions on multi-agent systems / LLM-tool integration under consideration.

## License

CC BY 4.0 for the paper text and figures (TODO: add `LICENSE` file at submission time).
