# Three-Axis Judge Reliability for Multi-Agent Eval Suites

Source for the research paper introducing the Blackrim eval-suite's
**three-axis methodology** for LLM-as-judge scoring: calibration-no-regression
(for classifier and pairwise rubric scorers), agreement-no-regression (for
rubric and trajectory-rubric scorers on subjective task shapes), and a
bias-bound precondition on every LLM-judge cell. Headline empirical
contribution: documenting that RLHF-tuned judges are systematically
worse-calibrated than their pretrained ancestors (Kadavath et al. 2022 +
follow-on calibration-degradation literature), with implications for any
team adopting forced-tool-use LLM judging on instruction-tuned models.

The paper is structurally distinct from the companion Blackrim model-advisor
paper: that work optimises a tier-cost-ratio decision rule under a single
quality-floor constraint; this work measures judge reliability under three
non-collapsible axes — calibration, agreement, and bias — applied per
(scorer-class × task-shape) cell.

## Build

LaTeX toolchain required (any of):

```bash
brew install --cask basictex          # ~100 MB — minimal but enough
brew install --cask mactex-no-gui     # ~5 GB — full TeX Live
# or use Overleaf (upload main.tex + sections/ + bib/ + ../_shared/)
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
├── bib/refs.bib                # BibTeX bibliography (paper-local entries)
├── figures/                    # TikZ + pgfplots sources
├── data/                       # CSV result files backing §6 figures/tables
└── scripts/                    # eval harness — reproduces data/ from raw telemetry
```

The bib also pulls in `../_shared/refs-base.bib` — a cross-paper bib carrying
conservative-bandit + general-ML citations shared with the model-advisor and
retriever papers.

## Reproducibility

Every quantitative claim in §6 (Empirical Evaluation) is backed by a CSV in
`data/` produced by a script in `scripts/`. The eval-suite paper-stream
telemetry (planned: `internal/eval/paper_stream.go`, mirroring the retriever
paper's `internal/bdmemory/paper_stream.go`) writes per-case records to
`data/raw/cases.jsonl`. To reproduce from scratch:

```bash
python scripts/pull-telemetry.py --since=30d > data/raw/cases.jsonl
python scripts/aggregate-by-cell.py < data/raw/cases.jsonl > data/aggregated/by-cell.csv
python scripts/run-calibration.py --judge=haiku-4-5 > data/aggregated/calibration.csv
python scripts/run-bias-diagnostic.py             > data/aggregated/bias.csv
make            # latex picks up new data/*.csv automatically via pgfplots
```

## Companion software

The paper describes the eval-suite as a system component of
[Blackrim](https://github.com/jsgerman-oss/blackrim.dev), specifically the
`internal/eval/`, `internal/scorer/`, and `evals/` paths. It draws on the deep
landscape research at `docs/research/eval-suite-landscape.md` (per-(scorer-class
× task-shape) calibration / agreement / bias priors anchored to Zheng,
Kadavath, Liu, and the CALM bias taxonomy) and the algorithm survey at
`docs/research/eval-suite-algorithms.md` (7 algorithm families surveyed;
top-3 v1 recommendation; honest reassessment of mean-of-means as the current
default aggregator).

## Status

Skeleton — sections are structure-only with `\tothink{}` placeholders. Full
prose drafting is sequenced behind the model-advisor and retriever papers.

## License

CC BY 4.0 for the paper text and figures. See `LICENSE` (TODO: add when ready
to publish).
