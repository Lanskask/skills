# youtube-to-course

Turns a YouTube video, a playlist, or a time range into the same kind of interactive HTML course as `book-to-course`.
Scripts do the mechanical work with no LLM; the model reads small digests and per-lesson transcript packs, and every
claim links back to a moment in the video.

## Use

```bash
make setup                                   # check tools
Y2C="uv run path/to/youtube-to-course/scripts/y2c.py"
$Y2C prepare "https://youtu.be/ID" --out ./talk-course            # whole video
$Y2C prepare "https://youtu.be/ID" --out ./talk-course --start 10:00 --end 45:00
$Y2C prepare "https://youtube.com/playlist?list=…" --out ./series-course --items 1-6
# the model writes work/outline.json from work/digest_all.md, then:
$Y2C validate --out ./talk-course --stage outline
$Y2C select   --out ./talk-course                                   # one pack per lesson
# the model writes work/drafts/L-xx.json from each pack, then:
$Y2C validate --out ./talk-course && $Y2C render --out ./talk-course   # open talk-course/index.html
$Y2C status   --out ./talk-course                                   # resume point
```

Other commands: `fetch | transcript | clean | segment | digest | frames` (single stages), `read` (logged full-text
fallback). `make test` runs the offline tests; `make demo` prepares a short TED talk.

### Dependencies

| Needed for                                          | Tool                                                                   | Notes                                                                                                     |
| --------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| everything                                          | `uv`, `yt-dlp`                                                         | Python ≥ 3.10; scripts use only the standard library                                                      |
| Whisper (only if no captions, or `--whisper force`) | `faster-whisper>=1.2`, `av>=16,<17`, `tokenizers>=0.21`, `onnxruntime` | installed by `uv` on first use into its cache; model download tiny 75 MB / small 460 MB; no ffmpeg needed |
| `--frames` (optional)                               | `ffmpeg` (works with 5.1+ `-fps_mode` and older `-vsync`), `tesseract` | needs a media download or `--video-file`                                                                  |
| tests                                               | `pytest`                                                               | `uv run --with pytest`                                                                                    |

If YouTube answers HTTP 403 to media downloads (Whisper audio, frames), captions and metadata still work. Give a local
file (`--audio-file`, `--video-file`) or set `Y2C_YTDLP_ARGS` (for example `--cookies-from-browser chrome`). That is
your decision; the skill never uses cookies by default.

## Token costs

All numbers are estimates at ~4 characters per token; real tokenizers differ by model.

**Measured** on an 8-minute TED talk with 7 creator chapters (1,235 spoken words, 3 lessons, run end to end in this
repo, `templates/example/`):

| Step                                                                      | Tokens                                              |
| ------------------------------------------------------------------------- | --------------------------------------------------- |
| Raw transcript with time markers (for comparison, never read as a whole)  | 2.1k                                                |
| Pass 1 reads `digest_all.md`                                              | 1.2k                                                |
| Pass 1 writes `outline.json`                                              | 0.4k                                                |
| Pass 2 reads 3 packs (complete, because the segments are small)           | 2.3k                                                |
| Pass 3 writes 3 lessons                                                   | 3.0k                                                |
| Once per course: SKILL.md + rubric, schemas, example, philosophy, gotchas | ~9k                                                 |
| **Total**                                                                 | **~18k (≈ 9k without the once-per-course reading)** |

On a short video the skill costs _more_ than pasting the transcript. It earns its cost from validation, links,
resumability, and consistency, not from tokens.

**Estimated** for longer input (extrapolated from the measured ratios: ~260 tokens per minute of speech with markers,
~175 tokens per digested segment, packs capped at 2.5k, ~1k per lesson written):

| Input                                                        | Raw transcript | Digest (Pass 1) | Packs (Pass 2)     | Lessons written | Once | Total         |
| ------------------------------------------------------------ | -------------- | --------------- | ------------------ | --------------- | ---- | ------------- |
| 1-hour talk, ~10–15 segments, ~8 lessons                     | ~16k           | 2–4k            | ~15–20k            | ~8k             | ~9k  | **~35–40k**   |
| 10-hour playlist (10 videos), ~100–250 segments, ~60 lessons | ~160k          | 18–45k          | ~100–150k (capped) | ~60k            | ~9k  | **~190–260k** |

What the design saves: nothing is read twice, the outline is built from digests alone, per-lesson packs are capped
(`--budget`), scripts remove noise, sponsors and duplicate caption lines (measured 0–5% of words on manual captions;
more on auto-captions), and the model never receives video frames. A coverage-complete course still has to read about as
much text as the transcript contains; for a 10-hour playlist lower the budget (`--budget 1500`) or limit scope
(`--items`, `--start/--end`) if cost matters. Whisper, frames and OCR cost CPU time and downloads, not tokens.

## Limits (read before promising anything)

- **No captions:** Whisper (local) transcribes. Speed depends on the machine (tiny is fast and rough, small is the
  default, medium is slow); technical terms and names are often wrong (measured: the `tiny` model wrote "Dubai length"
  for "Debye length"). The pipeline cannot know; it flags look-alikes from the title/description/chapters. A course from
  such a transcript needs human review of terms.
- **Mostly visual videos** (live coding, whiteboard, demos, slides read aloud): the transcript holds only what was said.
  Code, formulas and diagrams on screen are missing unless `--frames` OCR caught them, and OCR is unreliable on
  handwriting, small text and video compression. Lessons must say "watch this moment" (with a link) instead of
  describing what the script cannot see. Music-only or silent videos produce nothing to teach.
- **Auto-captions:** no punctuation quality, wrong homophones, ±5 s timing. Quote checks use the transcript as it is, so
  a correct term cannot be quoted when the captions garbled it.
- **Sponsor/filler removal is heuristic.** It is reported in `clean_report.json` and reversible, and it can miss or cut
  real content.
- **Timestamps are approximate** (a few seconds), because cues are re-grouped.
- **What was and was not tested end to end:** captions, chapters, playlist, time range, topic split, auto-captions and
  Whisper (on a local audio file) ran on real videos. `--frames` + OCR ran on a _synthetic_ two-slide video through
  `--video-file` (both slide changes found at the right seconds, text read with one `0`/`O` slip). It has not run on a
  real lecture recording, and YouTube returned HTTP 403 for every media download when tested here, so the YouTube audio
  and video download paths are untested. Frame defaults (`--threshold 0.05`) come from that one synthetic test: a text
  change on a white slide scores far below the usual 0.3, so de-duplication by OCR text (not the scene score) does the
  filtering.

## Consistency across LLMs

Guaranteed by scripts (identical for any model): the segments and their ids, the digest, the packs, the schema of
outline and lessons, coverage of every segment, citation validity (whole seconds inside the lesson's segments), quote
fidelity, length/quote-share limits, and the HTML. Varies by model: which segments are grouped into which lesson, the
teaching quality, metaphors, quiz difficulty, how well garbled terms are repaired, whether `read` is used when a pack
has gaps, and whether the lesson is faithful beyond what the checks can see (a paraphrase can still be wrong while every
timestamp is valid).
