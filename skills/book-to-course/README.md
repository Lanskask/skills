# Book to Course

Based on [zarazhangrui/codebase-to-course](https://github.com/zarazhangrui/codebase-to-course): it reuses that skill's
course format, styles and scripts, with a new pipeline for PDF books.

A Claude Code skill that turns a large PDF book (or a page/chapter range) into an interactive HTML course in the same
format as [`codebase-to-course`](https://github.com/zarazhangrui/codebase-to-course): scroll modules, quizzes, glossary
tooltips, source ↔ plain-words blocks, plus a glossary module. Built so the LLM **never reads the whole book**.

## Quick start

```bash
make setup                       # needs uv; tesseract optional (scanned PDFs)
make test                        # 101 pytest tests on synthetic books
make demo                        # prepare a sample book, validate + render two example lessons, open index.html
```

In Claude Code, say: _"make a course from ~/books/some-book.pdf, chapters 3-5"_ or _"…pages 120-180"_. See `SKILL.md`
for the workflow.

Dependencies: Python ≥ 3.10, `uv` (resolves **PyMuPDF** per script run; AGPL-licensed), optional `tesseract` (+
`rus`/`eng` data) for OCR. Everything else is the standard library.

## How it saves tokens

| Step                                    | Who        | Reads                                         | Typical size             |
| --------------------------------------- | ---------- | --------------------------------------------- | ------------------------ |
| prepare (extract, clean, split, digest) | scripts    | the PDF                                       | 0 LLM tokens             |
| Pass 1 outline                          | LLM        | `digest_all.md` (TOC + ≤ 450 tok per chapter) | ~10k for a 500-page book |
| Pass 2 per lesson                       | LLM        | `selections/L-xx.md` (budget 1800 tok)        | ~1.8k × lessons          |
| Fallback                                | LLM        | `read --chapter --pages` (capped, logged)     | only when `needs_more`   |
| Pass 3 per lesson                       | LLM writes | rubric/schema once, draft JSON out            | ~2-3k output per lesson  |
| validate / render                       | scripts    | drafts                                        | 0 LLM tokens             |

### Measured on the synthetic sample (`make sample`, 39 pages, English)

Run on this machine; token counts use the skill's own estimator (≈ 4 chars/token), not a model tokenizer.

- Whole book: ~29k tokens. `digest_all.md` (5 chapters + TOC): ~2.3k tokens, 8% of the book.
- One lesson pack: ~1.8k tokens out of ~3.3k available for its pages.

### One real measurement (user report, Claude Code on Sonnet 5.5)

A ~30-page scope (3 chapters, ~9k tokens of source, ~8 lessons, math, code and problems) cost about **$3.45
API-equivalent**: 97k output tokens, 8.5M cache-read tokens, 196k cache-write tokens, in a 1 h wall-clock session; that
was **12 points of the 5-hour session** and **2 points of the weekly limit** on their plan. That is about 2.5x my
earlier estimate (~$1-1.5): the agent loop re-reads its context on every tool call, and lessons plus validate/fix loops
produced about 3x the output I assumed. For a scope this small the packs plus full reads (~23k tokens) cost more than
the source itself (9.4k): see "Small scope" in SKILL.md.

### Estimated for a 500-page book (extrapolation, not measured; probably low by ~2x given the measurement above)

Assumptions: ~400 words/page → ~270k tokens raw; 20 chapters; 24 lessons; 25% of lessons need a ~3k-token full read.

|                            | Raw read                         | This skill                                                                                    |
| -------------------------- | -------------------------------- | --------------------------------------------------------------------------------------------- |
| Book input read by the LLM | ~270k (does not fit one context) | ~10k digests + ~43k packs + ~18k fallbacks ≈ **70k**                                          |
| + fixed templates/rubric   | –                                | ~5k once (up to ~120k if every lesson starts in a fresh context; prompt caching reduces this) |
| LLM output                 | same                             | ~3k outline + ~60k lessons                                                                    |

A 40-page chapter range: ~3k digest + 3-4 lessons × 1.8k ≈ **10k input**. Costs scale linearly with the range. Raise
`--budget` (more text per lesson) or `--digest-budget` for quality; lower for cost.

## Formulas (LaTeX)

- **Recovering them from the PDF:** display equations are detected (math fonts/characters, short, not prose), numbered
  `ch03-e01`, and given a **machine-drafted LaTeX** built from the text layer: sub/superscripts from font size and
  baseline, Greek letters and operators from Unicode. Packs carry them as `[EQ id · p.N · eq.(n)] draft: $…$`;
  `b2c.py eq --id … --image` crops the formula picture and `b2c.py page-image` renders a page, so the model can _look_
  at a formula (a few hundred tokens) instead of reading pages. No ML OCR model is bundled (pix2tex/Nougat/Marker need
  PyTorch and GPUs).
- **Writing them in lessons:** `math` blocks (display) and `$…$` (inline, also in quizzes) with a required symbol table;
  formulas are `book` (checked against the cited page and `eq` id) or `derived` (labelled "derived here" in the course).
  The validator checks LaTeX structure and KaTeX-unsupported commands.
- **Showing them:** KaTeX 0.16 from the jsDelivr CDN (needs internet like the Google Fonts already used); the course
  contains `book-math.js` only when math is used. Verified in Chrome on the sample course: 16/16 formulas rendered,
  including math injected into quiz feedback.
- **Limits:** drafts are wrong for fractions (`a / b`), matrices, stacked limits, accents/vectors and multi-line
  derivations; scanned books give OCR text, not LaTeX. Grounding is loose (distinctive symbols on the page), so a model
  can still mistype a formula that shares symbols with the printed one. If you have the book's `.tex` source, use it
  instead of the PDF (not supported by this skill).

## Pictures, diagrams, exercises

- **Book figures** (`figure` block): found by their captions (`ch03-f02`), cropped from the PDF on demand
  (`b2c.py fig --id … --image` to look, rendered into `figures/`).
- **Diagrams drawn by the course** (`diagram` block): `flow` (algorithms, loops, cause→effect) and `plot` (y = f(x)
  curves, log axes, points) from a small JSON spec, rendered as themed SVG by script, so every model gets the same
  drawing for the same spec; labelled "Illustration made for this course". Expressions are whitelisted (no code
  execution).
- **Exercises** (`task` block): book problems copied verbatim (≤ 120 words, checked against the page) with a plain-words
  restatement and optional hint.
- **Pages from the contents**: `prepare --printed-pages 123-154` (or `pagemap`) converts printed page numbers to PDF
  pages.
- Seen in Chrome on the sample course: the plot and flow diagram render, with distinguishable curves (colour + dash
  style).

## Course interface

- **Home**: a cover page (`#home`) with title, stats, module cards and a Start button; the Home button in the top bar
  returns to it, and ↑ from module 1 goes there.
- **Contents**: a slide-over drawer (button in the top bar or on the cover) listing modules, lessons and the glossary,
  with a reading-progress meter, a ✓ on lessons already passed, and the current lesson highlighted (`aria-current`).
  Esc, the backdrop or choosing a link closes it; focus moves in, is trapped, and returns; the page behind is inert.
- **Dark/light theme**: follows your system by default; the sun/moon button switches and remembers the choice
  (localStorage, guarded for private mode); choosing your system's theme again returns to "follow the system". Applied
  before first paint, so no flash.
- **Accessibility and robustness**: skip link, visible focus rings, 40 px targets, `aria-pressed` switch with a constant
  label, WCAG AA contrast checked in tests for all five accent colours in both themes (white-on-accent fills are
  darkened slightly to reach 4.6:1), reduced-motion and print styles, no-JS fallback, localised labels.
- Opens by double-clicking `index.html` (classic scripts, no modules, no fetch). Internet is only needed for the Google
  Fonts and KaTeX CDNs; without it the page falls back to system fonts and raw `$TeX$`. Tested in Chrome through a local
  server; I have not opened it via `file://` myself.

## What you get on disk

```
<course>/ styles.css main.js book-extras.css _base.html _footer.html build.sh index.html  modules/*.html
<course>/work/ manifest.json structure.json digest_all.md digests/ chapters/ selections/ outline.json drafts/ eq/ fig/ (crops, on demand) report.json usage.jsonl
```

Delete `work/` to start over; keep it to let another model resume (`b2c.py status`).

## What is and is not guaranteed

**Guaranteed by scripts (identical for every model):** the extracted/cleaned text, chapter split, manifest, digests and
packs (same input → same bytes); the outline/lesson schemas; every chapter covered or explicitly skipped; every
objective covered by a screen; every citation inside the lesson's source pages and on a page with text; every quote
verbatim, ≤ 25 words and ≤ 15% of a lesson; no long verbatim copying; valid quiz indexes; every `[[term]]` defined; the
same HTML/CSS/JS.

**Not guaranteed (varies by model and run):** wording, metaphors, which objectives a model derives from digests,
difficulty and quality of quiz questions, whether a paraphrase is faithful to the page (the validator cannot read
meaning), pedagogical order. Bit-identical output across different LLMs is impossible; the design makes the _structure,
coverage and grounding_ comparable.

**Trade-offs of reading digests/packs instead of the book:** extractive summaries favour frequent terms and miss rare,
once-stated facts, derivations, worked examples, tables and figures (only captions are seen). Packs are keyword-ranked,
so a lesson with vague objectives gets a weaker pack. Pass 1 may mis-weight chapters it only saw through a 450-token
digest. The skill reads more when `needs_more=True` (term coverage < 60%, no paragraph matches, OCR'd book), when the
lesson is about a derivation/table/example, or when the structure confidence is low; those reads are capped, logged and
shown in `report.json`.

**Known limits:** two-column layouts and tables may interleave; equations are mangled text; scanned books depend on OCR
quality; books without an outline use heading heuristics (tested only on synthetic and simple layouts), and fall back to
fixed page chunks; the heading fallback can merge back matter such as an index into the last chapter; titles that break
across pages or sit inside images are not detected. Hyphenated compounds split at a line end ("quasi-/neutral") are
joined without the hyphen.

## Type-checking the browser JS

`assets/book-ui.js` and `assets/book-math.js` start with `// @ts-check` and use JSDoc types, so editors flag mistakes
with no build step. `make typecheck-js` runs `tsc` (via `npx`, needs node) in strict mode against them using
`tsconfig.json`. `main.js` is a verbatim copy and is not checked.
