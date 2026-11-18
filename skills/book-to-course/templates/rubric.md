# Lesson rubric

A lesson is good when every line below is true. Lines marked **[script]** are checked by `b2c.py validate`; the rest are
for you (the writing model) to check before saving the draft.

## Grounding

1. **[script]** Every screen carries at least one page citation, and every citation lies inside the lesson's
   `source_refs` pages and points at a page that has extracted text.
2. **[script]** Quotes are verbatim (checked against the page text), at most 25 words, at most 15% of the lesson.
3. **[script]** No run of 25+ words is copied outside a quote block (12+ is a warning). Paraphrase.
4. Nothing in the lesson is stated that the pack/pages do not support. If the pack was too thin, read the exact pages
   with `b2c.py read` and list them in `sources.read_full` with the reason. Never fill gaps from memory and cite a page
   for them.
5. Anything you add beyond the book (an analogy, a general fact) is in the `metaphor` or clearly worded as "think of it
   as"; it carries no page citation.

## Teaching

6. **[script]** Every objective is covered by at least one screen (`covers`).
7. One concept per screen; 2-6 screens; a text block is at most 90 words (**[script]**).
8. **[script]** Every screen has at least one non-text block (cards, steps, quote, callout). Visual first.
9. Open with a hook tied to something the learner knows; give a fresh metaphor that fits _this_ concept (never
   restaurant/kitchen; never reuse one from another lesson).
10. Define every non-obvious term the first time with `[[term]]` and a glossary entry (**[script]** for missing
    entries). Define for a reader who knows little yet: no jargon without a definition.
11. Connect abstract ideas to something the reader can do or check (a number, a decision, a situation from their own
    life or work).
12. At most two callouts per lesson.

## Formulas (LaTeX)

16. **[script]** Display formulas use a `math` block, inline ones `$...$` (a literal dollar is `\\$`). In the JSON file
    every backslash is doubled (`"\\frac{a}{b}"`). No `$$` in running text. LaTeX must pass the structural check
    (**[script]**: braces, `\left/\right`, environments, `\frac` arity, KaTeX-unsupported commands like `\bm`, `\label`,
    `\newcommand`; use `\boldsymbol`, `\notag`, written-out expressions).
17. Every `math` block says where it comes from: `origin: "book"` (**[script]**: its Greek letters, `∑∫√` and numbers
    must appear on the cited page, and on the `eq` id's page if given) or `origin: "derived"` (you derived it; needs a
    caption saying from what; shown as "derived here"). Never present your own formula as the book's.
18. Machine-drafted LaTeX is not trusted: for any formula with fractions, matrices, multi-line layout or an OCR'd page,
    open the crop (`b2c.py eq --id … --image`) and correct the draft before using it.
19. **[script warns]** Name every symbol once in `symbols` (LaTeX in `sym`, plain words in `meaning`). Say in words what
    the formula says, what happens when one quantity grows, and, where it helps, a number the learner can check. Do not retype
    a derivation; cite its pages.
20. Quiz questions about formulas ask for a _prediction_ ("what happens to $\\lambda_D$ if the density quadruples?"),
    not for recalling the formula. Math is allowed in questions, options and explanations. Glossary definitions and
    tooltips are plain text (**[script]**).

## Visuals and readability

21. Every lesson has at least one figure or diagram (**[script warns]**), and no screen is text-only (**[script]**). Prefer
    a drawing to a paragraph when the idea is a process (flow), a dependence (plot), a geometry or apparatus (book figure),
    or a comparison (cards).
22. **[script]** A `figure` block needs an existing figure id on the cited page, a caption in your own words, and a
    croppable graphic. Look at the crop before using it.
23. **[script]** `diagram`s validate: unique node ids, edges that point to real nodes, whitelisted plot expressions
    defined on the range, plain-text labels. A diagram is your illustration of an idea from the cited page; the page
    labels it as such. Do not draw data the book does not support as if it were measured.
24. Short sentences, one idea per block, define each term at first use, keep labels in diagrams to a few words.
25. **[script]** `task` blocks: statement verbatim and ≤ 120 words, restated in plain words (≥ 6) at the lesson's level;
    Problems are never solved from memory.

## Code, problems and clean text

26. **[script]** `code` blocks: verbatim from the page (whitespace ignored), ≤ 30 lines, each `lines[].at` inside the
    listing, every explanation at least 4 words. Explain what the code does and why, not just "this line prints"; point
    out Python 2 vs 3 differences in `note`, never silently change the code.
27. **[script]** Garbled text in a verbatim `quote`/`task` (x2 for x², fractions lost, `…`): keep the verbatim text as
    printed and add `shown` with the repaired version ($LaTeX$). `shown` may fix formatting and math only; it must keep
    the words (85% match). Repair math by looking at the page image, not by guessing.

## Quiz

13. **[script]** 1-5 questions, 3-5 distinct options, valid answer index, both explanations present, citation.
14. Questions present a new scenario and ask the learner to _apply_ the idea, not recall a name or a page. Wrong options
    are plausible mistakes, not jokes. Vary the answer position.

## Honesty

15. If the source is ambiguous, wrong, or outdated, say so in a callout (variant `warning`) instead of smoothing it
    over.
