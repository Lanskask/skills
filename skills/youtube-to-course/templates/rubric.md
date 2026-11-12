# Lesson rubric

A lesson is good when every line below is true. Lines marked **[script]** are checked by `y2c.py validate`; the rest are for you (the writing model) to check before saving the draft.

## Grounding
1. **[script]** Every screen carries at least one timestamp, and every timestamp lies inside the lesson's segments (±10 s), inside the video, and is a whole number of seconds.
2. **[script]** Quotes are found in the transcript within 30 s before / 45 s after `at` (≥ 90% of their words, in order), at most 25 words, at most 15% of the lesson.
3. **[script]** No run of 25+ words is copied from the transcript outside a quote block (12+ is a warning). Paraphrase.
4. Nothing is stated that the pack does not support. If the pack was too thin (`needs_more=True`, or `[… omitted …]` hides what you need), run `y2c.py read --segment sNNN --from … --to …`
   and list the range in `sources.read_full` with the reason. Never fill gaps from memory and cite a timestamp for them.
5. Anything you add beyond the video (an analogy, a general fact) lives in the `metaphor` or is worded as "think of it as"; it carries no timestamp.
6. **Transcript errors**: auto-captions and Whisper garble technical terms ("Dubai length" for "Debye length"). Check the digest's `check (maybe mis-heard)` lines and the video description.
   Use the correct term in your text; if you are not sure, say so in a `warning` callout. Never build a lesson on a term you suspect is garbled without flagging it.
7. If the video is mostly visual at that point (the speaker says "as you can see here"), say what you cannot know from the transcript instead of guessing.

## Teaching
8. **[script]** Every objective is covered by at least one screen (`covers`).
9. One concept per screen; 2-6 screens; a text block is at most 90 words (**[script]**).
10. **[script]** Every screen has at least one non-text block (cards, steps, quote, callout, diagram, math). Visual first.
11. Open with a hook tied to something the learner knows; give a fresh metaphor that fits *this* concept (never restaurant/kitchen; never reuse one from another lesson).
12. Define every non-obvious term at first use with `[[term]]` and a glossary entry (**[script]** for missing entries), for a reader who knows little yet.
13. Connect abstract ideas to something the reader can do or check (a number, a command, an experiment).
14. At most two callouts per lesson.

## Formulas (LaTeX)
15. **[script]** Display formulas use a `math` block, inline ones `$...$` (literal dollar: `\\$`). In JSON every backslash is doubled. LaTeX passes the structural check (braces, `\left/\right`, environments, `\frac` arity, KaTeX-unsupported commands).
16. A `math` block says where it comes from: `video` (shown/said; **[script warns]** unless `checked_against: "screen"`) or `derived` (your own; needs a caption saying from what; shown as "derived here").
17. Name every symbol once in `symbols`. Say in words what the formula says and what happens when one quantity grows.

## Visuals and readability
18. Every lesson has at least one diagram (**[script warns]**), and no screen is text-only (**[script]**). Prefer a drawing when the idea is a process (flow) or a dependence (plot), or a comparison (cards).
19. **[script]** Diagrams validate: unique node ids, edges to real nodes, whitelisted plot expressions defined on the range, plain-text labels. A diagram is your illustration; the page labels it so. Never draw data the speaker did not give as if it were measured.
20. Short sentences, one idea per block, labels of a few words.

## Quiz
21. **[script]** 1-5 questions, 3-5 distinct options, valid answer index, both explanations, a timestamp.
22. Questions present a new scenario and ask the learner to *apply* the idea, not recall a name or a minute. Wrong options are plausible mistakes. Vary the answer position.

## Honesty
23. If the speaker is wrong, outdated, selling something, or contradicts another segment, say so in a `warning` callout instead of smoothing it over.
