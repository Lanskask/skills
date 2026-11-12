# Gotchas (video edition)

- **Timestamps are approximate.** Caption cues start at a time; the clean step spreads words evenly inside a cue. Expect ±5 s. Validator slack is 10 s. Links open a few seconds early or late.
- **Auto-captions/Whisper garble terms.** Digest lines `check (maybe mis-heard)` list words within edit distance of words in the title/description/chapters. Fix spelling in your lesson; never copy the garbled spelling into a `quote` unless it is verbatim (quotes are matched against the transcript as it is).
- **Quotes must match the transcript, not reality.** If the transcript has "Dubai length", a quote of "Debye length" fails validation. Quote only clean sentences; paraphrase the rest.
- **Chapters are the creator's, not yours.** A chapter may be 30 seconds (marked `minor`, not required) or 40 minutes (split into parts automatically).
- **Sponsor removal is a heuristic.** `clean_report.json` lists removed runs (≥ 3 promo keywords in 30 s). If a real passage was dropped, re-run `clean --keep-sponsors`.
- **Playlists:** segment ids are global (s001…), video ids v01…; a module = one video. Two modules can share one video, never the reverse.
- **Time-range scope** (`--start/--end`): captions are cut to the range; a chapter that straddles the edge is clipped. A clipped sliver under 60 words is `minor`.
- **Re-running `prepare` on the same `--out`** regenerates segments with the same ids only if the input and scope are unchanged. Changing the scope invalidates outline and drafts.
- **YouTube may answer 403 to media downloads** (Whisper audio, frames). Captions and metadata still work. Use `--audio-file/--video-file` or `Y2C_YTDLP_ARGS`.
- **A broken Homebrew ffmpeg** (`Library not loaded: libx265`) breaks `--frames` only. `brew reinstall ffmpeg`.
- **Music / no speech:** Whisper returns few or no cues; segments become `minor`; the validator then reports the video has nothing to cover. Say so to the user rather than inventing content.
- **Languages:** captions language = video language, or `--lang`. Course language follows the transcript (en/ru). Digest/stopword lists exist for en and ru only; other languages work but rank worse.
