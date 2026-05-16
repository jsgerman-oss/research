PAPER := main
SECTIONS := $(wildcard sections/*.tex)
BIB := bib/refs.bib
FIGURES := $(wildcard figures/*.tex)

.PHONY: all clean watch view distclean lint wordcount data fidelity-dryrun

all: $(PAPER).pdf

$(PAPER).pdf: $(PAPER).tex $(SECTIONS) $(BIB) $(FIGURES)
	latexmk -pdf -bibtex -halt-on-error -interaction=nonstopmode $(PAPER).tex

watch:
	latexmk -pdf -bibtex -pvc -halt-on-error -interaction=nonstopmode $(PAPER).tex

view: $(PAPER).pdf
	open $(PAPER).pdf

clean:
	latexmk -c $(PAPER).tex
	rm -f *.bbl *.run.xml *.synctex.gz

distclean:
	latexmk -C $(PAPER).tex
	rm -f *.bbl *.run.xml *.synctex.gz

lint:
	-chktex -q $(PAPER).tex sections/*.tex 2>&1 | head -50
	-lacheck $(PAPER).tex 2>&1 | head -50

wordcount:
	@texcount -inc -sum -1 $(PAPER).tex 2>/dev/null || echo "install texcount: brew install texcount or use texlive"

BLACKRIM_REPO ?= /Users/jayse/Code/blackrim
TELEMETRY_SINCE ?= 2026-05-09T03:17:00-07:00

# Pull live telemetry from the Blackrim repo and regenerate the CSV.
# Requires git access to BLACKRIM_REPO (default: /Users/jayse/Code/blackrim).
# Override: make data BLACKRIM_REPO=/path/to/blackrim
data: data/aggregated
	python scripts/pull-telemetry.py \
		--since "$(TELEMETRY_SINCE)" \
		--repo "$(BLACKRIM_REPO)" \
		> data/raw/session-telemetry.json
	python scripts/aggregate-trim-results.py \
		< data/raw/session-telemetry.json \
		> data/aggregated/trim-results.csv

data/aggregated:
	mkdir -p data/aggregated

# Smoke-test the fidelity eval harness (no API key required)
# Runs dry-run against both the baseline SHA and the Wave-2 SHA recorded
# in data/aggregated/trim-results.csv.
BASELINE_SHA := 6414995
WAVE2_SHA    := 6c7f3a0
EVAL_PROMPTS := scripts/eval-fidelity/prompts.yml

fidelity-dryrun:
	python scripts/eval-fidelity/run.py \
		--prefix-sha $(BASELINE_SHA) \
		--prompts $(EVAL_PROMPTS) \
		--dry-run \
		--out data/aggregated/fidelity-$(BASELINE_SHA)-dryrun.csv
	python scripts/eval-fidelity/run.py \
		--prefix-sha $(WAVE2_SHA) \
		--prompts $(EVAL_PROMPTS) \
		--dry-run \
		--out data/aggregated/fidelity-$(WAVE2_SHA)-dryrun.csv
	@echo "fidelity-dryrun complete — CSVs in data/aggregated/"
