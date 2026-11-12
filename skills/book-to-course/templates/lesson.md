# Lesson draft skeleton (JSON; schema: lesson.schema.json; worked example: example/L-01.json)

```json
{
  "id": "L-01",
  "title": "…",
  "metaphor": "one sentence, fresh, fits this concept",
  "hook": "one sentence tied to something the learner already knows",
  "why_care": "one sentence: what this lets the learner do or check",
  "screens": [
    {
      "id": "s1", "heading": "…", "covers": [0],
      "blocks": [
        {"type": "text",    "text": "… [[term]] …", "cite": [41]},
        {"type": "cards",   "items": [{"title": "…", "text": "…", "icon": "🔬"}, {"title": "…", "text": "…"}], "cite": [41, 42]},
        {"type": "steps",   "items": [{"title": "…", "text": "…"}, {"title": "…", "text": "…"}], "cite": [43]},
        {"type": "quote",   "text": "verbatim, ≤ 25 words", "page": 44, "meaning": "plain-language translation"},
        {"type": "math",    "origin": "book", "eq": "ch03-e01", "cite": [44],
         "latex": "\\lambda_D = \\sqrt{\\frac{\\epsilon_0 k_B T_e}{n e^{2}}}",
         "caption": "optional one-line reading of the formula",
         "symbols": [{"sym": "\\lambda_D", "meaning": "the [[Debye length]]"}, {"sym": "n", "meaning": "electron density"}]},
        {"type": "figure",  "fig": "ch03-f02", "page": 45, "caption": "what the figure shows, in your words (≥ 5 words)"},
        {"type": "diagram", "kind": "flow", "title": "…", "caption": "…", "cite": [45], "direction": "LR",
         "nodes": [{"id": "a", "label": "Assign charge"}, {"id": "b", "label": "Solve field"}],
         "edges": [{"from": "a", "to": "b", "label": "optional"}, {"from": "b", "to": "a"}]},
        {"type": "diagram", "kind": "plot", "title": "…", "caption": "…", "cite": [45],
         "x": {"label": "r (units of λD)", "min": 0.2, "max": 5}, "y": {"label": "potential", "scale": "linear"},
         "series": [{"label": "1/r", "expr": "1/x"}, {"label": "e^(−r)/r", "expr": "exp(-x)/x"}], "points": []},
        {"type": "code",    "lang": "python", "page": 126, "code": "import random\ncount = 0",
         "lines": [{"at": "1", "text": "what line 1 does, in plain words"}, {"at": "2-3", "text": "what these lines do"}], "note": "optional"},
        {"type": "task",    "page": 46, "statement": "problem text as printed (≤ 120 words, garbled math is fine)", "shown": "optional clean version, math as $LaTeX$",
         "plain": "what it asks, in your own words, at the lesson's level", "hint": "optional"},
        {"type": "callout", "variant": "accent|info|warning", "title": "…", "text": "…", "cite": [45]}
      ]
    }
  ],
  "quiz": [{"question": "scenario …?", "options": ["…", "…", "…"], "answer": 1,
            "explain_right": "…", "explain_wrong": "…", "cite": [44]}],
  "glossary": [{"term": "term", "definition": "plain words, ≤ 60", "cite": [44]}],
  "key_takeaways": ["…", "…"],
  "sources": {"chapters": ["ch03"], "read_full": [{"chapter": "ch03", "pages": "44-46", "reason": "pack lacked the derivation"}]}
}
```
`quote` and `task` take an optional `shown`: the clean display version (math as `$LaTeX$`) of a verbatim `text`/`statement` whose math is garbled in the text layer.
`math` takes optional `checked_against: "image"` when you compared the formula with the crop/page image because the text layer lost symbols.
`code` copies a listing verbatim (≤ 30 lines, `...` lines allowed) with per-line plain-English `lines`.
Visuals: `figure` shows a cropped book figure (id from the pack's `[FIG …]` lines; page must match). `diagram` is drawn from the spec (plain-text labels, no `$math$`;
powers as `**`). `task` copies a book problem verbatim and restates it. See SKILL.md Step 3c/3d.
Math: display formulas are `math` blocks; inline math is `$...$` inside any text/title/quiz string (`\\$` is a literal dollar).
JSON needs doubled backslashes. `origin` is `book` (needs page cite, optional `eq` id from `b2c.py eq --list`) or `derived` (your own;
needs `cite` of the pages it builds on and a `caption`). `symbols` is required (1-10). Glossary definitions must not contain math.
Rules: page numbers are PDF page indexes (`p.N` in the pack). `sources.chapters` must equal the chapter ids in the
lesson's `source_refs`. Block types are exactly: text, cards, steps, quote, math, figure, diagram, code, task, callout. Use `quote` for the "source ↔ plain words"
translation block (the book's analogue of code ↔ English).
