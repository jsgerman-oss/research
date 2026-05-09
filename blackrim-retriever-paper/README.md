# Adaptive Conservative Selection for Hybrid Retrieval in Multi-Agent Memory Systems

Source for the research paper introducing the Blackrim retriever — a per-query-class adaptive policy for combining BM25, SPLADE, dense retrieval, RRF fusion, recency decay, MMR, and an optional cross-encoder reranker, formalised as a conservative contextual bandit with a per-class baseline (BM25 / BM25+decay) safety constraint.

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

The bib also pulls in `../_shared/refs-base.bib` — a cross-paper bib carrying conservative-bandit + general-ML citations shared with the model-advisor paper.

## Reproducibility

Every quantitative claim in §6 (Empirical Evaluation) is backed by a CSV in `data/` produced by a script in `scripts/`. The retriever paper-stream telemetry (`internal/bdmemory/paper_stream.go`) writes per-query records to `data/raw/queries.jsonl`. To reproduce from scratch:

```bash
python scripts/pull-telemetry.py --since=30d > data/raw/queries.jsonl
python scripts/aggregate-by-class.py < data/raw/queries.jsonl > data/aggregated/by-class.csv
python scripts/run-eval-suite.py --policy=conservative-cb > data/aggregated/eval-results.csv
make            # latex picks up new data/*.csv automatically via pgfplots
```

## Companion software

The paper describes the retriever as a system component of [Blackrim](https://github.com/jsgerman-oss/blackrim.dev), specifically the `internal/bdmemory/` package (BM25, SPLADE, dense, RRF, decay, MMR, reranker) and the paper-stream telemetry path in `internal/bdmemory/paper_stream.go` that writes per-query records to `data/raw/queries.jsonl`. The paper draws on the deep landscape research at `docs/research/retriever-landscape.md` (per-(query-class × scorer-family × fusion-config) priors) and the algorithm survey at `docs/research/retriever-algorithms.md` (9 algorithm families surveyed; top-3 recommendation; honest reassessment of the current stack).

## Status

Skeleton — sections are structure-only with `\tothink{}` placeholders. Full prose drafting is sequenced after the model-advisor paper goes to arXiv.

## License

CC BY 4.0 for the paper text and figures. See `LICENSE` (TODO: add when ready to publish).
