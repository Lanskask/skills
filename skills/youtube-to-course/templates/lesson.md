# Lesson draft skeleton (JSON; schema: lesson.schema.json; worked examples: example/L-01.json … L-03.json)

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
        {"type": "text",    "text": "… [[term]] …", "cite": [61, 73]},
        {"type": "cards",   "items": [{"title": "…", "text": "…", "icon": "🧠"}, {"title": "…", "text": "…"}], "cite": [82, 118]},
        {"type": "steps",   "items": [{"title": "…", "text": "…"}, {"title": "…", "text": "…"}], "cite": [302, 309]},
        {"type": "quote",   "text": "verbatim from the pack, ≤ 25 words", "at": 26, "speaker": "optional, default = channel", "meaning": "plain-language translation"},
        {"type": "math",    "origin": "video|derived", "latex": "E = mc^{2}", "cite": [300], "caption": "required if derived",
         "symbols": [{"sym": "E", "meaning": "energy"}], "checked_against": "screen"},
        {"type": "diagram", "kind": "flow", "title": "…", "caption": "…", "cite": [45], "direction": "LR",
         "nodes": [{"id": "a", "label": "Assign charge"}, {"id": "b", "label": "Solve field"}],
         "edges": [{"from": "a", "to": "b", "label": "optional"}, {"from": "b", "to": "a"}]},
        {"type": "diagram", "kind": "plot", "title": "…", "caption": "…", "cite": [45],
         "x": {"label": "r", "min": 0.2, "max": 5}, "y": {"label": "potential", "scale": "linear"},
         "series": [{"label": "1/r", "expr": "1/x"}], "points": []},
        {"type": "callout", "variant": "accent|info|warning", "title": "…", "text": "…", "cite": [45]}
      ]
    }
  ],
  "quiz": [{"question": "scenario …?", "options": ["…", "…", "…"], "answer": 1,
            "explain_right": "…", "explain_wrong": "…", "cite": [61]}],
  "glossary": [{"term": "term", "definition": "plain words, ≤ 60", "cite": [61]}],
  "key_takeaways": ["…", "…"],
  "sources": {"segments": ["s001", "s002"], "read_full": [{"segment": "s002", "range": "1:30-2:10", "reason": "pack had a gap"}]}
}
```
Rules
- **Times are whole seconds in the lesson's video**: the number after `|` in the pack's `[m:ss|sec]` markers. `cite` is a list of them, `quote.at` a single one.
  The page renders each as a link `https://youtu.be/ID?t=SEC`. A lesson uses one video (its module's).
- Block types are exactly: text, cards, steps, quote, math, diagram, callout. `quote` is the "speaker ↔ plain words" block.
- `[[term]]` marks the first use of a term; every marked term needs a `glossary` entry (plain text, no math).
- `sources.segments` must equal the segments in the lesson's `source_refs`.
- Math: display formulas in `math` blocks, inline `$...$`, doubled backslashes in JSON. `origin: video` means the formula is shown or said in the video;
  audio rarely carries symbols, so add `checked_against: "screen"` only when an `[on-screen]` line in the pack shows it. Otherwise it is `derived` (needs a caption).
- Diagram labels are plain text (no `$math$`); plots use `x pi e sin cos tan exp log sqrt abs sinh cosh tanh + - * / **` only.
