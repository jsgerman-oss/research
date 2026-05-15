# The AST as LLM Lens

Source for the research paper introducing **outline-first reading** and **compile-gated symbolic surgery** as Blackrim's AST-native code surface for multi-agent LLM workflows. The paper formalises the AST as the primary lens through which LLM agents read and modify code, reports measured cross-language compression ratios (Go 82.0%, Python 84.1%, JavaScript 83.0%, TypeScript 75.2% token savings on realistic files), and lays out the empirical programme for the still-unmeasured claims (outline-discipline hit-rate, end-to-end token reduction on real traces, refactor false-negative rate).

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
make data       # regenerate CSVs from a Blackrim checkout (needs gt on PATH)
```

## Layout

```
.
├── main.tex                    # master — \input's section files
├── Makefile                    # latexmk + lint + wordcount + data targets
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
└── scripts/                    # harness — reproduces data/ from a Blackrim checkout
```

## Reproducibility

Every quantitative claim in §6 (Empirical Evaluation) is backed by a CSV in `data/` produced by a script in `scripts/`. To reproduce from scratch (assumes a Blackrim checkout at `$BLACKRIM_ROOT`, default `$HOME/Code/blackrim`, with `gt` on PATH):

```bash
make data       # runs the four aggregation scripts; emits CSVs in data/aggregated/
make            # latex picks up new data/*.csv automatically via pgfplots
```

The pipeline is deterministic given (a) a Blackrim checkout at a fixed commit and (b) the test corpus pinned in `scripts/corpus.txt`. The published version anchors to a tagged Blackrim commit.

### Currently measured (real numbers)

- **§6.2 — Compression ratios by language.** Backed by `data/aggregated/by-language.csv`, produced by `pull-compression-ratios.py` + `aggregate-by-language.py` reading the bench fixtures at `cmd/gt/testdata/bench/` and the per-language compression backends. Reproduces the ratios reported in ADR 0002.

### Pending (placeholders in the draft)

The remaining empirical claims are marked with `\tothink{}` in the LaTeX. They will be filled as the following telemetry and evaluation work lands:

- **§6.3 — Outline token-budget conformance.** Pending: corpus run over the Go standard library + selected polyglot repos; target ~300-token outline budget, measured at 95th percentile.
- **§6.4 — Latency of outline emission.** Pending: `measure-outline-latency.py` runs `gt outline` over files of size 100 → 5000 LoC and records wall-clock.
- **§6.5 — Outline-discipline adoption trajectory.** Pending: `.beads/telemetry/outline-events.jsonl` must accumulate two weeks of data before the warn→auto→block path's hit-rate trajectory can be plotted.
- **§6.6 — Symbolic surgery false-negative rate.** Pending: refactor-eval harness over a curated rename/move/replace corpus.
- **§6.7 — End-to-end token reduction on real agent traces.** Pending: instrumented `Read` vs. `gt outline` paired traces from production Explore-tier dispatches.

The transparency about what is and isn't measured is intentional — see §1.3 (Methodological stance) and §6 opening.

## Companion software

The paper describes the AST surface as a system component of [Blackrim](https://github.com/jsgerman-oss/blackrim.dev). Reference implementations:

- `cmd/gt/outline/` — Phase 1a outline emitter (Go).
- `cmd/gt/compress_structure*.go` — polyglot compression backends (Go, Python, JavaScript, TypeScript). The canonical pre-outline emitter; merging into `gt outline --bulk` in Phase 1b.
- `internal/codeindex/refactor/` — LSP-driven Tier-1 symbolic refactors.
- `internal/codeindex/symbol/` — per-language tree-sitter symbol extractors.
- `hooks-staging/outline-discipline.sh` — the warn→auto→block hook.
- `skills/read-with-outline/SKILL.md` — the agent-facing skill.

The paper draws on the design spec at `docs/specs/blackrim-ast-outline-and-surgery.md` (and its architecture-review companion), the ADR at `docs/adr/0002-polyglot-ast-structure-compression.md`, and the codeindex spec at `docs/specs/codeindex.md`.

## Status

Draft. Not yet peer-reviewed. Targeting arxiv preprint as the first submission; venue candidates: ICSE Companion, FSE Industry Track, or PLDI tools.

## License

CC BY 4.0 for the paper text and figures. See `LICENSE` (TODO: add when ready to publish).
