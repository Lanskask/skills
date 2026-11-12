# Everyday commands for youtube-to-course. Scripts run through `uv`, which resolves their dependencies.
Y2C = uv run scripts/y2c.py
URL ?= https://www.youtube.com/watch?v=-FOCpMAww28
OUT ?= ./sample-course

.PHONY: setup test lint demo clean
setup:            ## check tools (yt-dlp required; ffmpeg+tesseract only for --frames; uv for everything)
	@for t in uv yt-dlp; do command -v $$t >/dev/null || { echo "MISSING: $$t"; exit 1; }; done
	@for t in ffmpeg tesseract; do command -v $$t >/dev/null && echo "ok: $$t" || echo "optional, missing: $$t (only needed for --frames)"; done
	@ffmpeg -version >/dev/null 2>&1 || echo "WARNING: ffmpeg is broken (brew reinstall ffmpeg); --frames will not work"
test:             ## unit tests (no network)
	uv run --with pytest python -m pytest tests -q
lint:
	uvx ruff check --select F,E9 scripts tests
demo:             ## prepare the sample video (network); then read $(OUT)/work/digest_all.md
	$(Y2C) prepare "$(URL)" --out $(OUT)
clean:
	rm -rf .pytest_cache .ruff_cache */__pycache__ */*/__pycache__
