# Gotchas (book edition)

- **Citing from memory.** The model "knows" the textbook and cites a page it never saw. Validation only proves the page
  is in range and quotes exist; it cannot prove a paraphrase is faithful. Write only what the pack supports; read more
  pages (and log them in `sources.read_full`) instead of guessing.
- **Digest ≠ book.** Digests are extractive: they favour frequent terms and miss derivations, worked examples,
  tables and anything stated once. Use them to plan, not to teach. Check `needs_more` on every pack.
- **PDF page ≠ printed page.** All citations are PDF page indexes. Do not "fix" them to the printed numbers.
- **Chapter ids depend on scope** when the structure came from headings or chunks; with a PDF outline they are stable.
  Re-run `prepare` with the same scope arguments or the outline's `source_refs` will not match.
- **Low-confidence structure.** `manifest.structure.confidence == "low"` means chunks of pages, not real chapters.
  Inspect `work/structure.json`, try `--structure headings`, or pass `--chunk-pages`.
- **Scanned books.** OCR errors corrupt quotes and symbols; the pack says so (`needs_more`). Prefer fewer, shorter quotes.
- **Machine-drafted LaTeX is a draft.** It comes from the text layer: sub/superscripts are reconstructed from font size and baseline, Greek/operators
  from Unicode. Fractions appear as `a / b`, stacked limits, matrices and multi-line derivations are flattened, accents/vectors are lost, and some PDFs
  map math glyphs to private codepoints (garbage or `?`). Open the crop (`b2c.py eq --id … --image`) before trusting a formula; on scanned books
  the draft is OCR text and often wrong. The validator checks structure and that distinctive symbols occur on the cited page; it cannot check that the
  formula is mathematically the same as the printed one.
- **JSON and LaTeX backslashes.** Every `\` in LaTeX is `\\` in the draft file; a single backslash before `f`, `t`, `b`, `r` or `n` silently becomes a form feed,
  tab, etc. (`"\frac"` is read as form-feed + `rac`). The validator rejects the resulting garbage, but write doubled backslashes from the start.
- **KaTeX, not full LaTeX.** No `\newcommand`, `\label`, `\bm`, `\SI`, packages or custom environments. Use `\boldsymbol`, `\mathrm{d}`, `\text{…}`.
  Rendering loads KaTeX from a CDN; offline, the page shows the raw `$…$` source.
- **Two-column layouts / tables** can interleave. If a pack reads oddly, `read` the page range and judge for yourself.
- **Header stripping is aggressive by design** (any line repeated on ≥ 3 pages in the margin band). If a real heading
  vanished, check `work/clean_report.json`.
- **Walls of text, recycled metaphors, memory-test quizzes, mandatory scroll-snap** — same rules as codebase-to-course
  (see `content-philosophy.md`).
- **Figures are found by captions.** A figure without a caption line (or with the caption in an image) has no id. Figures made of scanned pixels, or drawn inside a full-page
  image, cannot be cropped; use a `diagram`. The crop is the graphics adjacent to the caption plus text inside it (axis labels); neighbouring panels sharing a
  caption may come out together.
- **Plots are illustrations.** The renderer labels them "Illustration made for this course". Do not plot invented numbers as if the book measured them; plot the book's formula.
- **Printed vs PDF pages again.** `--printed-pages` needs readable page numbers in the margins; books with roman-numeral front matter work, but a book with unnumbered
  chapter-opening pages gives fewer samples (still fine with >= 3 agreeing pages). Whole chapters: prefer `--chapters`.
- **Accents and ligatures.** `ﬀ ﬁ ﬂ` are expanded and a spacing diaeresis/acute/circumflex before a vowel is composed (`Schr¨odinger` becomes `Schrödinger`). Backticks are left alone because of code listings.
- **Math-font false positives (fixed).** `CMR/CMBX/CMTI/CMSS` are LaTeX *text* fonts; only `CMMI/CMSY/CMEX` (+ AMS symbol and "Math" fonts) mark math. When every body line counted as math, short code and prose
  lines became `[EQ …]`. Code is now detected by monospace fonts first.
- **Equations in several lines/blocks** (a derivation) are merged into one `eq` when the lines are within 16 pt of each other; separated displays stay separate. Check `eq --list` if ids look fragmented.
- **Running heads.** Margin lines are removed when they sit in the top/bottom 9%, or are among the first/last two lines of the page and carry a number that follows the page index (`124 …`, `… 125`),
  or repeat on >= 40% of pages. Labels like `Chapter 1`, `Chapter 2` are not removed (their digit does not follow the page). Check `work/clean_report.json` after `prepare`.
- **Packs can still miss a paragraph** when the lesson is big: gap markers now say what is missing (`[… 3 paragraph(s) omitted (p.5: mersenne, twister, period) …]`); read those pages if they matter.
