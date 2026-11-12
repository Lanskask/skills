---
name: youtube-to-course
description:
  "Turn a YouTube video, a playlist, or a time range of a video into a beautiful interactive HTML course, without ever
  watching or reading the raw video. Use when someone wants a course, study guide, lessons, quiz or tutorial from a
  YouTube link, lecture, talk, conference session, tutorial series or playlist, e.g. 'turn this video into a course',
  'make lessons from this YouTube lecture', 'course from minutes 10-45 of this video', 'learn from this playlist',
  'study guide from this talk'. Scripts fetch metadata, get the transcript (manual captions, then auto-captions, then
  local Whisper), clean it, split it by the creator's chapters or by topic shifts, and build digests with no LLM; the
  model reads digests (Pass 1), then one transcript pack per lesson (Pass 2), and every lesson links back to the moment
  in the video (youtu.be/ID?t=SECONDS)."
---

# YouTube-to-Course

Converts a YouTube video (or playlist, or a start/end range) into the same kind of course `book-to-course` produces
(scroll modules, quizzes, glossary tooltips, speaker ↔ plain-words blocks), **without the model ever watching the video
or reading a whole transcript**. Scripts do all mechanical work; you read small, fixed-format artifacts in three passes
and write schema-checked lessons grounded in timestamps.

Shorthand (all commands are deterministic; none call an LLM):

```bash
Y2C="uv run <skill-dir>/scripts/y2c.py"  # <skill-dir> = this skill's base directory, shown when the skill loads; uv installs deps
OUT=./<slug>-course                                              # course dir in the CURRENT folder; work files live in $OUT/work
```

Needs `yt-dlp` and `uv`. `ffmpeg` + `tesseract` only for `--frames`. Whisper installs itself on first use
(`faster-whisper`, a model download: tiny 75 MB, small 460 MB). `make setup` in the skill dir checks tools.

## Who this is for

A learner who knows little yet. Define every term at first use, tie ideas to something they can run or check, write in
the **video's language** (en/ru auto-detected). Read `references/content-philosophy.md` before Pass 1.

## Hard rules (what keeps results consistent across models)

1. **Never read `work/segments/*` or `cues*.json` wholesale, never open the video.** Read only `work/digest_all.md`
   (Pass 1), `work/selections/L-xx.md` (Pass 2) and ranges fetched with `$Y2C read` (logged fallback).
2. **Every artifact is a file** with a fixed schema. Another model can resume from `$Y2C status --out $OUT`.
3. **Nothing is final until `$Y2C validate` passes.** Fix and re-run; do not argue with the validator.
4. **Cite whole seconds** exactly as printed after `|` in the pack markers (`[4:55|295]` → 295). Never cite from memory.
   Every citation becomes a `youtu.be/ID?t=SEC` link.
5. Quotes: verbatim from the pack, ≤ 25 words, rare. Paraphrase everything else.
6. **Transcripts can be wrong** (auto-captions, Whisper). Use the digest's `check (maybe mis-heard)` hints and the
   description; flag doubt in a `warning` callout. Never invent what a visual showed.

## Workflow

### Step 0 — Scope

Input: a URL (video, playlist, or 11-char id), optional range, optional language. Turn the request into flags:

- one video: `URL`; part of a video: `--start 10:00 --end 45:00` (seconds, M:SS, H:MM:SS or 1h2m3s); only that range is
  transcribed, segmented and covered.
- playlist: `URL [--items 1-5,8] [--max-videos N]` → one module per video, shared glossary. `--start/--end` do not apply
  to playlists.
- `--lang xx` to force the caption language; `--whisper auto|off|force` (default `auto` = only when no captions exist);
  `--model tiny|base|small|medium` (default small).
- `--frames` only for slide/code/whiteboard videos (needs a media download; see Gotchas). Before a long job, say what it
  will cost: run `fetch` (cheap: metadata only) and use the numbers in README "Token costs". Do not ask the user to
  approve the outline. **Whisper is slow and downloads a model: tell the user before running `--whisper force` or on a
  video with no captions; show the command if it could take more than a few minutes.**

### Step 1 — Prepare (scripts only)

```bash
$Y2C prepare "<URL>" --out $OUT [--start T --end T] [--items …] [--lang xx] [--whisper auto] [--frames]
```

= fetch → transcript → clean → (frames) → segment → digest. Check the printed summary:

- `transcript` source per video: `manual` (best), `auto` (expect garbled terms), `whisper` (expect garbled names/terms;
  check language).
- word counts before/after cleaning, sponsor runs removed (`work/vNN/clean_report.json`), segment table (`chapter` or
  `topic` split, `minor` segments are optional).
- If a video has no speech/captions or the segment list looks wrong, stop and tell the user. Stages can be re-run alone:
  `fetch | transcript | clean | segment | digest | frames`.

### Step 2 — Pass 1: outline (read `work/digest_all.md` only)

~150–200 tokens per segment. Design modules → lessons (fewer, better), arc from motivation to mechanism to limits. Write
`work/outline.json` per `templates/outline.schema.json` (worked example: `templates/example/outline.json`). **One module
= one video** (a long video may have several modules; a playlist has at least one per video). Per lesson: 2–5 objectives
starting with explain / apply / compare… (not "understand"), and `source_refs: [{segment, keywords}]`. You may reorder
segments within a video (say so in the module subtitle). **Every `content` segment must appear in a lesson or in
`skipped` with a reason** (ads, chit-chat, outro).

```bash
$Y2C validate --out $OUT --stage outline
```

### Step 3 — Pass 2: transcript packs (scripts select; you read one pack per lesson)

```bash
$Y2C select --out $OUT [--lesson L-01] [--budget 2500]
```

`work/selections/L-01.md`: the lesson's segments in time order with `[m:ss|sec]` markers; `[on-screen]` lines (OCR) if
`--frames` was used. Header: `complete=True` means the whole text of the lesson's segments is there. If
**`needs_more=True`** or `[… omitted N words …]` hides something the lesson needs:

```bash
$Y2C read --out $OUT --segment s003 --from 2:10 --to 3:40 [--max-tokens 4000]
```

Read the narrowest range and record it in the draft's `sources.read_full` (segment, range, reason).

### Step 4 — Pass 3: write the lesson (`work/drafts/L-xx.json`)

Read once per course: `templates/rubric.md`, `templates/lesson.md`, `templates/lesson.schema.json`,
`templates/example/L-01.json`, `references/gotchas.md`. Per lesson write the JSON, then:

```bash
$Y2C validate --out $OUT --stage lesson --lesson L-01
```

Block types: `text, cards, steps, quote, math, diagram (flow|plot), callout`. Aim for a diagram or cards on most
screens. Write lessons one at a time. Repeat until `[ok]`; `$Y2C status --out $OUT` lists each lesson as todo /
pack-ready / draft-invalid / validated, so a different model can continue. **Parallel path (6+ modules):** write
`work/briefs/Mx.md` from `templates/module-brief.md`; subagents get only their brief, their packs and the template
files; you re-run the course check.

### Step 5 — Self-check and render

```bash
$Y2C validate --out $OUT        # whole course: outline coverage, every lesson, at least one quote per module
$Y2C render --out $OUT          # validates, writes modules/*.html + index.html (glossary module included); --partial while iterating
```

`work/report.json` has errors/warnings and estimated token usage. Open `$OUT/index.html`, walk the user through it, say
which lessons needed `read`, which transcripts were auto/Whisper, and state limits honestly (README "Limits").

## What the validator guarantees

Schema; every `content` segment covered; every objective covered by a screen; every citation a whole second inside the
lesson's segments (±10 s) and inside the video; every quote found in the transcript near its timestamp (≥ 90% of words),
≤ 25 words, ≤ 15% of a lesson; no 25-word copy outside quotes; glossary/term/quiz sanity; diagram and LaTeX structure;
one video per module. It does **not** guarantee the lesson is correct, well taught, or that a garbled term was fixed
correctly.

## Files

- `scripts/y2c.py` + `scripts/y2c_lib/` — `fetch, transcript, clean, frames, segment, digest, select, validate, render`
  (+ `diagrams`, `mathtex`, `ui` copied from book-to-course); `scripts/whisper_worker.py` — local ASR
- `templates/` — `outline.schema.json`, `lesson.schema.json`, `lesson.md`, `rubric.md`, `module-brief.md`, `example/` (a
  real 3-lesson course on an 8-minute talk)
- `assets/` — `course.css` (the page design), `course-ui.js` (theme, contents, quizzes); `references/` —
  `content-philosophy.md`, `gotchas.md`
- `tests/` — pytest, offline (`make test`); `Makefile`; `README.md` — usage, token costs, limits; `DECISIONS.md` — why
  it is built this way
