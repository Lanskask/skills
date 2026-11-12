---
name: book-to-course
description: "Turn a large PDF book (or a page/chapter range of it) into a beautiful interactive HTML course, reading as little of the book as possible. Use when someone wants a course, study guide, lessons, or interactive tutorial from a PDF book, textbook, manual, or long report, e.g. 'turn this book into a course', 'make lessons from chapters 3-5', 'course from pages 120-180 of this PDF', 'teach me this textbook', 'interactive study guide from a PDF'. Scripts do extraction, header/footer cleaning, chapter splitting, digests and validation with no LLM; the model reads only the TOC + digests, then per-lesson passage packs, and every lesson cites PDF pages. Output matches codebase-to-course (same HTML, quizzes, glossary tooltips)."
---

# Book-to-Course

Converts a PDF book into the same kind of course `codebase-to-course` produces (scroll modules, quizzes, glossary tooltips,
source ↔ plain-words blocks), **without ever reading the whole book**. Scripts do all mechanical work; you read small,
fixed-format artifacts in three passes and write schema-checked lessons grounded in cited pages.

Shorthand used below (all commands are deterministic; none call an LLM):
```bash
B2C="uv run <skill-dir>/scripts/b2c.py"  # <skill-dir> = this skill's base directory, shown when the skill loads; uv resolves deps (pymupdf)
OUT=./<book-slug>-course                                       # course dir in the CURRENT folder; work files live in $OUT/work
```
Works from any folder: the scripts are called by absolute path, and nothing needs `cd` into the skill. First run installs PyMuPDF via `uv` (a few seconds).
`tesseract` (optional) enables OCR for scanned PDFs. Run `make setup` in the skill dir to check tools.

## Who this is for
A learner who knows little yet. Define every term the first time ("null space", "Z-pinch", "Adam"), tie ideas to something
they can run or check, write in the **book's language** (en/ru auto-detected, user can override). Read
`references/content-philosophy.md` before Pass 1.

## Hard rules (what keeps results consistent across models)
1. **Never open the PDF or `work/chapters/*` wholesale.** Read only: `work/digest_all.md` (Pass 1), `work/selections/L-xx.md`
   (Pass 2), and pages fetched with `$B2C read` (fallback, logged).
2. **Every artifact is a file** with a fixed schema. Another model can resume from `$B2C status`.
3. **Nothing is final until `$B2C validate` passes.** Fix and re-run; do not argue with the validator.
4. **Cite PDF page numbers (`p.N`)** exactly as they appear in the pack markers. Never cite from memory.
5. Quotes: verbatim, ≤ 25 words, rare. Paraphrase everything else.

## Workflow

### Step 0 — Scope
Input: PDF path (may contain spaces: quote it), optional scope, optional language. The user may give the scope as a pasted table-of-contents excerpt
("6 Monte Carlo Techniques 123 … 8 Partial Differential Equations 141 … Problems 153"). Turn it into one of:
- `--chapters 14-16`: **preferred for whole chapters.** Ids `ch03`… come from `$B2C outline book.pdf` (they count front matter such as Contents/Preface, so the
  book's "Chapter 1" is usually `ch03`); match the user's chapter titles to that list. This also gets the chapter ends right.
- `--printed-pages 123-154`: page numbers as printed in the book's contents; the script maps them to PDF pages (`$B2C pagemap book.pdf --printed 123-154` previews it)
  and refuses if the printed numbers are not consistent. When the user means whole chapters, end the range at the page before the next chapter starts, not at the
  last page they listed.
- `--pages 135-166`: PDF page numbers, always works.
- **No bookmarks** (`outline` prints "no usable PDF outline"): `$B2C find book.pdf "Monte Carlo Techniques" "Stochastic Methods"` lists where headings appear
  (PDF page, heading-like or not); then `--pages`, or `--printed-pages 123-154 --anchor "Monte Carlo Techniques"` (offset taken from that heading).
  `pagemap` reads page numbers from the margins, including running heads like `124   Monte Carlo Techniques` where the number is a separate text run.
- **Small scope** (`prepare` prints a NOTE when the scope is under ~25k tokens): reading it directly costs about the same as digests + packs, and `select` then returns
  *complete* packs (no gaps) for lessons whose pages fit. The skill still adds citations, validation, figures, code blocks and rendering. Say so to the user.
If the user gave no range and the book is long, run Step 1 anyway (it is cheap), look at `book_tokens_est` and the chapter
list, and say what the whole book would cost; proceed on the whole book only if they want it.

### Step 1 — Prepare (scripts only)
```bash
$B2C prepare book.pdf --out $OUT [--pages A-B | --chapters N-M] [--ocr auto|off|force] [--structure auto|outline|headings|chunks]
```
Produces `work/{pages,pages_clean,chapters,digests,manifest.json,structure.json,digest_all.md,clean_report.json}`.
Check the printed summary: `structure` source/confidence, chapter list with page ranges, `ocr_pages`. If confidence is **low** or
chapters look wrong, re-run with `--structure headings` or `--chunk-pages N`, or ask the user for a page range. Do not continue
on a structure you do not trust.

### Step 2 — Pass 1: outline (read `work/digest_all.md` only)
Typical size: ~2k tokens per 5 chapters. Design 4-8 modules × 2-6 lessons (fewer, better), arc from motivation to mechanism to
limits. Write `work/outline.json` following `templates/outline.schema.json`; worked example: `templates/example/outline.json`.
Per lesson: 2-5 objectives starting with verbs like explain / derive / compare / apply (not "understand"), and `source_refs`
(`chapter`, optional `pages`, optional `keywords` to steer Pass 2). **Every chapter of kind `chapter` must appear in some lesson or
in `skipped` with a reason.** Do not ask the user to approve the outline; build it.
```bash
$B2C validate --out $OUT --stage outline     # schema, ids, page ranges, chapter coverage
```

### Step 3 — Pass 2: passage packs (scripts select; you read one pack per lesson)
```bash
$B2C select --out $OUT --lesson L-01 [--budget 1800]     # or omit --lesson for all
```
Read `work/selections/L-01.md` (~1.8k tokens, document order, `<!-- p.N -->` markers, `[… omitted …]` gaps).
Look at the header: **`needs_more=True`** (low term coverage, no match, OCR) means the digest/pack is not enough. Then, and only then:
```bash
$B2C read --out $OUT --chapter ch03 --pages 44-46 [--max-tokens 4000]
```
Read the narrowest range that answers your gap and record it in the draft's `sources.read_full` with a reason.
If a derivation, table or worked example is the lesson's point, reading that page range is expected, not a failure.

### Step 3b — Formulas (LaTeX)
Display equations are detected by script (math fonts/characters, short, not prose), numbered `chNN-eMM`, and appear in packs as
`[EQ ch03-e01 · p.4 · eq.(1.1)] draft: $\lambda_{D} = \sqrt{…}$`. The LaTeX after `draft:` is **machine-built from the PDF text layer**
(sub/superscripts from font size and baseline, Greek/operators from Unicode). It is a starting point, never ground truth:
```bash
$B2C eq --out $OUT --chapter ch03 --list            # all drafted equations of a chapter (id, page, number, draft)
$B2C eq --out $OUT --id ch03-e01 --image            # draft + a cropped PNG of the formula: open the PNG with the Read tool
$B2C page-image --out $OUT --page 44                # whole page as PNG (scanned books, fractions/matrices the draft cannot express)
```
Look at the image whenever the draft contains `/` for a fraction, `?`/odd characters, spans several lines, or the book was OCR'd
(then the draft is OCR text). Reading a PNG costs far fewer tokens than reading pages. Write the corrected LaTeX in the lesson.
Use a `math` block for display formulas and `$...$` inline; rules in `templates/rubric.md` and `templates/lesson.md`.

### Step 3c — Pictures and diagrams (make the course visual)
Aim for at least one visual per lesson, and per screen where the idea allows. Three kinds, all grounded:
1. **Book figures**: packs list `[FIG ch03-f02 · p.5] Figure 1.2. …` for the lesson's pages. Look first: `$B2C fig --out $OUT --id ch03-f02 --image`
   (open the PNG). Worth showing when it is a real graphic (plot, apparatus, geometry, grid). Use a `figure` block with a caption in your own words.
   The renderer crops it from the PDF into `$OUT/figures/`. Not croppable (scanned, embedded in the page) means the validator says so: use a `diagram`.
   Figures are for personal study material; do not republish a book's figures.
2. **Flow diagrams** (`diagram` kind `flow`): algorithms, pipelines, cause→effect chains, loops ("assign charge → solve field → push → repeat"). 2-10 nodes,
   labels ≤ 44 chars, a back edge draws the repeat.
3. **Plots** (`diagram` kind `plot`): 1-4 curves `y = f(x)` (+ points) for a formula the lesson explains (decay, screening, scaling), linear or log axes.
   Expressions use `x pi e sin cos tan exp log sqrt abs sinh cosh tanh + - * / **` only. The page labels diagrams "Illustration made for this course",
   so they are never mistaken for the book's figures; cite the page whose idea they show.
Also use `cards`, `steps`, `callout` and `math` blocks to break up text (rubric: at most 2-3 sentences in a row).

### Step 3b' — Code listings
Monospace paragraphs are detected as code (never as equations) and appear in packs as `[CODE ch06-c02 · p.126]` with indentation rebuilt from the page geometry.
Show the part a lesson explains with a `code` block: `code` copied verbatim from the page (≤ 30 lines, whitespace ignored, `...` lines allowed), `lang`, `page`, and
`lines`: plain-English explanations per line or range (`{"at": "2-3", "text": "…"}`), optional `note` (e.g. "the book's listings are Python 2"). It renders like the
code ↔ English blocks of codebase-to-course. Do not fix or modernise the code inside `code`; say so in `note`.

### Step 3d — Exercises ("Problems" sections)
If the scope includes a Problems/Exercises section, keep it: one lesson (or the last screen of each lesson) with a `task` block per problem. Copy the statement
as it is printed (≤ 120 words; checked against the page by its 3+-letter words, so garbled math symbols in the text layer are fine), then put the clean, readable version in
`shown`: same words, math written as LaTeX (`$x^2 + y^2 = r^2$`; fractions and symbols the extractor lost such as `…` or `(1)` get repaired from the page image: look at
`b2c.py page-image`). `shown` must not reword (checked, 85% word match) and is what the learner sees; the raw text is only the proof. Then `plain`: restate in your own words what is asked and which idea from the lessons it uses,
at the same level as the rest of the course. Optional `hint`. Do not invent answers; only give a worked answer if the book prints it (then cite the page).

### Step 4 — Pass 3: write the lesson (`work/drafts/L-xx.json`)
Read once per course: `templates/rubric.md`, `templates/lesson.md`, `templates/lesson.schema.json`, `templates/example/L-01.json`,
`references/content-philosophy.md`, `references/gotchas.md`. Then per lesson write the JSON and run:
```bash
$B2C validate --out $OUT --stage lesson --lesson L-01
```
For formulas the validator checks: LaTeX structure (braces, `\left/\right`, environments, `\frac` arity, commands KaTeX lacks such as `\bm`),
that a `book` formula's distinctive symbols (Greek letters, `∑ ∫ √`, numbers) appear on the cited page and match its `eq` id, and that every Greek letter is
explained in `symbols`. Text layers lose `∑` (becomes "X"), drop `∫`, and print `ℏ` as `¯h`; these symbols are not used as evidence, and Δ/∆, ℏ/¯h variants are unified. If a
book formula still fails the symbol check, look at the equation crop or page image, and add `"checked_against": "image"` to the block (it stays `origin: "book"` and is
reported as accepted-by-image). Formulas you derive yourself must be `origin: "derived"` (the page then labels them "derived here"). Citations may use any page of a chapter the lesson cites (outside its `source_refs.pages` that is a warning; pages you list in `sources.read_full` count as source pages); a page of another chapter is an error. Repeat until `[ok]`. Resumable: `$B2C status --out $OUT` lists each lesson as todo / pack-ready / draft-invalid / validated;
skip validated ones. Write lessons one at a time (later lessons get thin when batched).

**Parallel path (6+ modules):** write `work/briefs/Mx.md` from `templates/module-brief.md`, dispatch up to 3 subagents, each
given only its brief, its packs and the template files above. They run `validate` themselves; you re-run the course check.

### Step 5 — Self-check and render
```bash
$B2C validate --out $OUT                    # whole course: outline coverage, every lesson, per-module quote requirement
$B2C render --out $OUT                      # validates again, writes modules/*.html, index.html (glossary module included)
```
`work/report.json` records errors/warnings and token usage (`select_tokens`, `full_read_tokens`). Open `$OUT/index.html` (double-click works). It has a cover/Home page, a Contents drawer, and a dark/light theme toggle.
Then walk the user through it, say which lessons needed full reads and why, and state limits honestly (see README).
Render only ready lessons while iterating: `render --partial`.

## Files
- `scripts/b2c.py` + `scripts/b2c_lib/` — pipeline (extract, clean, structure, split, digest, select, validate, render; `pagemap`, `eq`, `fig`, `page-image` helpers; `diagrams.py` draws SVG)
- `scripts/make_sample_pdf.py` — synthetic test books; `tests/` — pytest; `Makefile` — setup/test/lint/demo
- `templates/` — `outline.schema.json`, `lesson.schema.json`, `lesson.md`, `rubric.md`, `module-brief.md`, `example/`
- `assets/` — `styles.css`, `main.js`, `_base.html`, `_footer.html` copied verbatim from codebase-to-course
- `references/` — `content-philosophy.md`, `gotchas.md` (book edition)
- `README.md` — usage and token costs; `DECISIONS.md` — why it is built this way
