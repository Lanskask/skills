# Content philosophy (book edition)

Same principles as `codebase-to-course`, adapted: the learner is reading *about a book*, not a codebase.
Read this when writing the outline (Pass 1) and each lesson (Pass 3).

- **Visual first.** No more than 2-3 sentences in a row. Turn lists of 3+ into `cards`, sequences into `steps`,
  the book's key sentence into a `quote` block with a plain-language `meaning`.
- **Source ↔ plain words** replaces code ↔ English: left side is a short verbatim quote with its page, right side
  says it the way you would to a friend. At least one per module.
- **One concept per screen.** If a screen needs two headings, make two screens.
- **Metaphors first, then reality.** A fresh metaphor per lesson, never restaurant/kitchen, never repeated.
  The metaphor is yours; it never carries a page citation.
- **Define for a beginner.** The first time a term appears, wrap it in `[[term]]` and add a glossary entry written for
  a student who knows little yet ("null space", "Z-pinch", "Adam"). Tie it to something the learner can run, plot or check.
- **Math and derivations.** Show the key formula as a `math` block (LaTeX, rendered by KaTeX) with a symbol table (every symbol named once, plain words).
  Say what the equation says in words, what changes if a quantity grows, and give a number the learner can check. Do not retype a derivation from
  the book; cite its pages and explain the idea. Mark anything you derive yourself `origin: "derived"`. Define each symbol for a student who knows little yet.
- **Quizzes test application**, not recall: a new scenario, plausible wrong options, an explanation for each outcome.
- **Be honest about the source.** Say when the book is dated, ambiguous or contradicts itself (callout `warning`).
- **Quote sparingly.** ≤ 25 words per quote, ≤ 15% of a lesson, always attributed (the renderer adds title and page).
- **Arc.** Start with what the learner already knows or wants, then peel layers: motivation → core idea → mechanism →
  worked consequence → limits/pitfalls. Group lessons into 4-8 modules; a module is 2-6 lessons.

## Visuals (book edition)
- **Three sources of pictures:** the book's own figures (`figure`, cropped from the PDF, cited), diagrams the course draws from a spec (`diagram` flow/plot, labelled as
  made for the course), and layout blocks (cards, steps, callouts). Prefer one visual per screen; a lesson without any figure or diagram is a smell.
- **When a picture earns its place:** a process or loop (flow), how one quantity depends on another (plot), geometry/apparatus/grids (book figure), parallel
  alternatives (cards). Not for decoration.
- **Readable:** one idea per block, 2-3 sentences before a visual break, a caption that says what to notice, 3-8 words per diagram label.
- **Exercises:** copy the book's problem verbatim as a `task`, then say in plain words what is asked and which lesson idea it uses. No invented solutions.
