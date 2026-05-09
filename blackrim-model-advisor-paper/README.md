# Conservative Adaptive Model-Tier Selection for Multi-Agent LLM Workflows

Source for the research paper introducing the Blackrim model-tier advisor — a Bayesian, conservatively-biased policy for routing LLM calls across agents to a cost-minimal model tier subject to a quality-preservation constraint.

## Build

LaTeX toolchain required (any of):

```bash
brew install --cask basictex          # ~100 MB — minimal but enough
brew install --cask mactex-no-gui     # ~5 GB — full TeX Live
# or use Overleaf (upload main.tex + sections/ + bib/)
```

Then:

```bash
make            # build main.pdf
make watch      # rebuild on change (latexmk -pvc)
make view       # open the PDF
make clean      # remove build artifacts
make wordcount  # texcount summary per section
make lint       # chktex + lacheck (soft-fail on missing tools)
```

## Layout

```
.
├── main.tex                    # master — \input's section files
├── Makefile                    # latexmk + lint + wordcount targets
├── README.md                   # this file
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
├── data/                       # CSV result files backing §6 figures/tables
└── scripts/                    # eval harness — reproduces data/ from raw telemetry
```

## Reproducibility

Every quantitative claim in §6 (Empirical Evaluation) is backed by a CSV in `data/` produced by a script in `scripts/`. To reproduce from scratch:

```bash
python scripts/pull-telemetry.py --since=30d > data/raw/telemetry.jsonl
python scripts/aggregate-by-shape.py < data/raw/telemetry.jsonl > data/aggregated/by-shape.csv
python scripts/run-eval-suite.py --advisor=conservative-ts > data/aggregated/eval-results.csv
make            # latex picks up new data/*.csv automatically via pgfplots
```

## Companion software

The paper describes the advisor as a system component of [Blackrim](https://github.com/jsgerman-oss/blackrim.dev), specifically `internal/dispatch/model.go` and the planned MOA-9 (Bayesian scoring) layer. The paper draws on the deep landscape research at `docs/research/model-advisor-deep-landscape.md` and the algorithm survey at `docs/research/model-advisor-algorithms.md`.

## Status

Draft. Not yet peer-reviewed. Targeting arxiv preprint as the first submission; workshop venues under consideration.

## License

CC BY 4.0 for the paper text and figures. See `LICENSE` (TODO: add when ready to publish).
