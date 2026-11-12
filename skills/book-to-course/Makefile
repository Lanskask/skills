# book-to-course: everyday commands. Requires uv (https://docs.astral.sh/uv/).
SCRIPTS := scripts
SAMPLE  := /tmp/b2c-sample

.PHONY: setup test lint typecheck-js sample demo clean
setup:    ## check tools (uv required; tesseract optional, only for scanned PDFs)
	@command -v uv >/dev/null || { echo "install uv first"; exit 1; }
	@command -v tesseract >/dev/null && echo "tesseract: ok" || echo "tesseract: missing (OCR for scanned PDFs disabled)"
	@uv run -q --with pymupdf python -c "import pymupdf; print('pymupdf', pymupdf.__version__)"
test:     ## run the pytest suite on synthetic books
	uv run -q --with pymupdf --with pytest pytest -q tests
lint:     ## syntax + type-ish check
	python3 -m compileall -q $(SCRIPTS) tests && uvx ruff check $(SCRIPTS) tests --select E9,F --ignore F401
typecheck-js: ## type-check assets/book-ui.js and book-math.js (// @ts-check + JSDoc, tsc via npx; needs node)
	@command -v npx >/dev/null || { echo "install node first"; exit 1; }
	npx -y -p typescript tsc -p .
sample:   ## build the synthetic sample books into $(SAMPLE)
	mkdir -p $(SAMPLE) && for k in en noout scan ru; do uv run -q $(SCRIPTS)/make_sample_pdf.py --kind $$k --out $(SAMPLE)/$$k.pdf; done
demo: sample  ## prepare the sample book, validate+render the bundled example lessons
	uv run -q $(SCRIPTS)/b2c.py prepare $(SAMPLE)/en.pdf --out $(SAMPLE)/course
	cp templates/example/outline.json $(SAMPLE)/course/work/outline.json
	cp templates/example/L-*.json $(SAMPLE)/course/work/drafts/
	uv run -q $(SCRIPTS)/b2c.py validate --out $(SAMPLE)/course
	uv run -q $(SCRIPTS)/b2c.py render --out $(SAMPLE)/course && open $(SAMPLE)/course/index.html
clean:
	rm -rf $(SAMPLE) .pytest_cache
