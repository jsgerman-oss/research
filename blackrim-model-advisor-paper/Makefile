PAPER := main
SECTIONS := $(wildcard sections/*.tex)
BIB := bib/refs.bib
FIGURES := $(wildcard figures/*.tex)

.PHONY: all clean watch view distclean lint wordcount

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

# Lint: chktex on TeX, languagetool on prose, lacheck for structural issues.
# Each fails soft so a missing tool doesn't break the rule.
lint:
	-chktex -q $(PAPER).tex sections/*.tex 2>&1 | head -50
	-lacheck $(PAPER).tex 2>&1 | head -50

wordcount:
	@texcount -inc -sum -1 $(PAPER).tex 2>/dev/null || echo "install texcount: brew install texcount or use texlive"
