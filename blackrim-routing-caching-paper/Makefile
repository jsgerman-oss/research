PAPER := main
SECTIONS := $(wildcard sections/*.tex)
BIB := bib/refs.bib
FIGURES := $(wildcard figures/*.tex)

.PHONY: all clean watch view distclean lint wordcount data data-cache

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

# Reproduce all data/aggregated/*.csv from data/raw/*.json
data: data-cache
	python scripts/aggregate-trim-results.py

# Pull + aggregate cache statistics from Blackrim telemetry
# Writes: data/raw/session-telemetry.json, data/aggregated/cache-stats.csv
data-cache:
	python scripts/pull-telemetry.py --since 2026-05-01 \
	  --repo /Users/jayse/Code/blackrim \
	  > data/raw/session-telemetry.json
	python scripts/aggregate-cache-stats.py \
	  < data/raw/session-telemetry.json \
	  > data/aggregated/cache-stats.csv
