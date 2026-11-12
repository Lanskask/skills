"""Stage 3 — clean the raw transcript. Deterministic, no LLM.

1. strip sound tags ([Music], (applause)), speaker chevrons (>>), filler words (um, uh, э-э)
2. merge caption fragments and remove rolling duplicates (auto-captions repeat the previous line's tail)
3. regroup into sentence-like lines of <= ~28 words, each keeping the start time of its first word
4. drop sponsor / self-promo stretches (dense keyword hits), listed in clean_report.json

work/vNN/cues.json = {"lines": [{"start","end","text"}]}
"""
from __future__ import annotations

import re

from .common import Work, norm_ws, read_json, write_json

TAGS = re.compile(r"\[[^\]]{0,40}\]|\((?:music|applause|laughter|laughs|inaudible|музыка|аплодисменты|смех)[^)]*\)", re.I)
CHEVRON = re.compile(r"(?:^|\s)>>+\s*|(?:^|\s)-\s(?=[A-ZА-Я])")
FILLER = re.compile(r"\b(?:um+|uh+|erm|hmm+|you know,?|i mean,?|э+м*|ну|эм+|ммм*)\b[,.]?\s*", re.I)
SPONSOR = re.compile(
    r"\b(?:sponsor(?:ed|s)?|brought to you by|use (?:the )?(?:code|promo)|promo code|discount code|link (?:is )?in the description|"
    r"free trial|subscribe|hit the bell|like and subscribe|patreon|check out my (?:course|merch)|"
    r"спонсор\w*|промокод\w*|ссылка в описании|подписывайтесь|подпишитесь|скидк\w+)\b", re.I)
MAX_LINE_WORDS = 28
SPONSOR_WINDOW = 30  # seconds
SPONSOR_MIN_HITS = 3


def _tidy(text: str) -> str:
    text = TAGS.sub(" ", text)
    text = CHEVRON.sub(" ", text)
    text = FILLER.sub(" ", text)
    return norm_ws(text)


def _drop_overlap(prev_tail: list[str], words: list[str]) -> list[str]:
    """Remove the longest prefix of `words` that equals a suffix of `prev_tail` (rolling captions)."""
    for k in range(min(len(prev_tail), len(words)), 0, -1):
        if [w.lower() for w in prev_tail[-k:]] == [w.lower() for w in words[:k]]:
            return words[k:]
    return words


def merge(cues: list[dict]) -> list[dict]:
    """Cues -> word stream with times -> lines. A word's time is its cue's start (good enough for ~5-10 s accuracy)."""
    stream: list[tuple[float, float, str]] = []
    tail: list[str] = []
    for c in sorted(cues, key=lambda c: (c["start"], c["end"])):
        words = _tidy(c["text"]).split()
        words = _drop_overlap(tail[-40:], words)
        if not words:
            continue
        n = len(words)
        dur = max(c["end"] - c["start"], 0.1)
        for i, w in enumerate(words):
            t = c["start"] + dur * i / n
            stream.append((t, c["end"], w))
        tail += words
    lines, cur, start, end = [], [], 0.0, 0.0
    for t, e, w in stream:
        if not cur:
            start = t
        cur.append(w)
        end = e
        done = w[-1] in ".!?…" and len(cur) >= 6
        if done or len(cur) >= MAX_LINE_WORDS:
            lines.append({"start": round(start, 1), "end": round(end, 1), "text": " ".join(cur)})
            cur = []
    if cur:
        lines.append({"start": round(start, 1), "end": round(end, 1), "text": " ".join(cur)})
    return lines


def drop_sponsors(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    """A 30 s window with >= 3 promo keyword hits marks the lines from its first to its last hit-line (clean lines around it stay).
    Maximal marked runs are dropped and reported."""
    hits = [len(SPONSOR.findall(ln["text"])) for ln in lines]
    bad = [False] * len(lines)
    for i, ln in enumerate(lines):
        win = [j for j, other in enumerate(lines) if ln["start"] <= other["start"] <= ln["start"] + SPONSOR_WINDOW]
        if sum(hits[j] for j in win) >= SPONSOR_MIN_HITS:
            with_hits = [j for j in win if hits[j]]
            for j in range(with_hits[0], with_hits[-1] + 1):
                bad[j] = True
    kept, removed, run = [], [], None
    for ln, b in zip(lines, bad):
        if b:
            run = run or {"start": ln["start"], "end": ln["end"], "words": 0, "sample": ln["text"][:80]}
            run["end"] = ln["end"]
            run["words"] += len(ln["text"].split())
        else:
            if run:
                removed.append(run)
                run = None
            kept.append(ln)
    if run:
        removed.append(run)
    return kept, removed


def clean(work: Work, vid: str, keep_sponsors: bool = False) -> dict:
    raw = read_json(work.vdir(vid) / "cues_raw.json")
    lines = merge(raw["cues"])
    removed: list[dict] = []
    if not keep_sponsors:
        lines, removed = drop_sponsors(lines)
    words_in = sum(len(c["text"].split()) for c in raw["cues"])
    words_out = sum(len(ln["text"].split()) for ln in lines)
    write_json(work.vdir(vid) / "cues.json", {"source": raw["source"], "language": raw["language"], "lines": lines})
    rep = {"video": vid, "source": raw["source"], "words_raw": words_in, "words_clean": words_out, "lines": len(lines),
           "sponsor_runs_removed": removed}
    write_json(work.vdir(vid) / "clean_report.json", rep)
    return rep
