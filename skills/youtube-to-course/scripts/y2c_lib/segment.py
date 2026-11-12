"""Stage 4 — split each video into segments (the unit the outline and the lessons refer to).

By the creator's chapters when present, otherwise by topic shifts (TextTiling-style: TF-IDF cosine between adjacent
windows + pauses). Over-long chapters are split the same way. Output: work/segments/sNNN.md and work/manifest.json.
Ids are global (s001, s002, ...) and assigned in video order, so they are stable for the same input.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .common import Work, detect_lang, fmt_time, read_json, tokens, write_json

TARGET_WORDS = 900       # preferred segment size (~6 min of speech)
MAX_WORDS = 1800
MIN_WORDS = 250          # topic segments shorter than this are merged
MINOR_WORDS = 60         # segments below this are kind=minor: not required to be covered by a lesson
WINDOW = 5               # lines per comparison window


def _tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    df: Counter = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)
    out = []
    for d in docs:
        tf = Counter(d)
        out.append({t: (1 + math.log(c)) * math.log((n + 1) / (df[t] + 0.5)) for t, c in tf.items()})
    return out


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    num = sum(v * b.get(k, 0.0) for k, v in a.items())
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def topic_boundaries(lines: list[dict], lang: str) -> list[int]:
    """Indices i such that a new segment starts at lines[i]. Deterministic."""
    n = len(lines)
    if n < 2 * WINDOW + 2:
        return []
    toks = [tokens(ln["text"], lang) for ln in lines]
    gaps = list(range(WINDOW, n - WINDOW + 1))
    left = [sum((toks[j] for j in range(g - WINDOW, g)), []) for g in gaps]
    right = [sum((toks[j] for j in range(g, g + WINDOW)), []) for g in gaps]
    vecs = _tfidf(left + right)
    sim = [_cos(vecs[i], vecs[len(gaps) + i]) for i in range(len(gaps))]
    # a pause before the line makes a boundary more likely
    score = []
    for k, g in enumerate(gaps):
        pause = max(0.0, lines[g]["start"] - lines[g - 1]["end"])
        score.append(1 - sim[k] + min(pause, 4.0) * 0.03)
    mean = sum(score) / len(score)
    sd = math.sqrt(sum((s - mean) ** 2 for s in score) / len(score))
    cand = [(score[k], gaps[k]) for k in range(len(gaps))
            if score[k] > mean + 0.5 * sd and (k == 0 or score[k] >= score[k - 1]) and (k == len(gaps) - 1 or score[k] >= score[k + 1])]
    words = [len(ln["text"].split()) for ln in lines]
    cum = [0]
    for w in words:
        cum.append(cum[-1] + w)
    chosen: list[int] = []
    for _, g in sorted(cand, reverse=True):  # strongest first, keep segments >= MIN_WORDS
        pts = sorted(chosen + [g])
        edges = [0] + pts + [n]
        if all(cum[edges[i + 1]] - cum[edges[i]] >= MIN_WORDS for i in range(len(edges) - 1)):
            chosen.append(g)
    # force splits of anything still longer than MAX_WORDS
    edges = [0] + sorted(chosen) + [n]
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        w = cum[b] - cum[a]
        if w > MAX_WORDS:
            k = math.ceil(w / TARGET_WORDS)
            for m in range(1, k):
                target = cum[a] + w * m / k
                chosen.append(min(range(a + 1, b), key=lambda j: abs(cum[j] - target)))
    return sorted(set(chosen))


def _keywords(lines: list[dict], lang: str, idf_docs: list[list[str]], k: int = 3) -> list[str]:
    """Most distinctive words of a segment, shown in their most frequent surface form (not the crude stem)."""
    text = " ".join(ln["text"] for ln in lines if not ln["text"].startswith("[on-screen]"))
    toks = tokens(text, lang)
    surface: dict[str, Counter] = {}
    for w in re.findall(r"[^\W\d_]+", text.lower()):
        t = tokens(w, lang)
        if t:
            surface.setdefault(t[0], Counter())[w] += 1
    df: Counter = Counter()
    for d in idf_docs:
        df.update(set(d))
    n = len(idf_docs) + 1
    tf = Counter(toks)
    ranked = sorted(tf, key=lambda t: (-(tf[t] * math.log(n / (df[t] + 0.5))), t))
    return [surface[t].most_common(1)[0][0] for t in ranked[:k] if t in surface]


def segment_video(meta: dict, lines: list[dict], lang: str) -> list[dict]:
    s, e = meta["scope"]
    lines = [ln for ln in lines if ln["end"] > s and ln["start"] < e]
    segs: list[dict] = []
    chapters = [c for c in meta["chapters"] if c["end"] > s and c["start"] < e]
    if chapters:
        for c in chapters:
            sub = [ln for ln in lines if c["start"] <= ln["start"] < c["end"]]
            if not sub:
                continue
            words = sum(len(ln["text"].split()) for ln in sub)
            pieces = [sub]
            if words > MAX_WORDS:
                cuts = [0] + topic_boundaries(sub, lang) + [len(sub)]
                pieces = [sub[cuts[i]:cuts[i + 1]] for i in range(len(cuts) - 1)]
            for i, p in enumerate(pieces):
                title = c["title"] if len(pieces) == 1 else f"{c['title']} (part {i + 1})"
                segs.append({"lines": p, "title": title, "source": "chapter"})
    else:
        cuts = [0] + topic_boundaries(lines, lang) + [len(lines)]
        docs = [tokens(ln["text"], lang) for ln in lines]
        for i in range(len(cuts) - 1):
            p = lines[cuts[i]:cuts[i + 1]]
            if p:
                kw = _keywords(p, lang, docs)
                segs.append({"lines": p, "title": ", ".join(kw) if kw else f"part {i + 1}", "source": "topic"})
    return segs


def segment_all(work: Work) -> dict:
    vids = read_json(work.videos)
    segdir = work.root / "segments"
    segdir.mkdir(parents=True, exist_ok=True)
    for old in segdir.glob("s*.md"):
        old.unlink()
    out_videos, out_segs, n = [], [], 0
    for meta in vids["videos"]:
        cues = read_json(work.vdir(meta["id"]) / "cues.json")
        fp = work.vdir(meta["id"]) / "frames.json"
        if fp.exists():  # on-screen text from `frames` is merged in as pseudo-lines (it counts as source text for packs and digests)
            extra = [{"start": float(f["t"]), "end": float(f["t"]), "text": "[on-screen] " + f["text"]} for f in read_json(fp)]
            cues["lines"] = sorted(cues["lines"] + extra, key=lambda ln: (ln["start"], ln["end"]))
        lang = detect_lang(" ".join(ln["text"] for ln in cues["lines"][:200]))
        for sg in segment_video(meta, cues["lines"], lang):
            n += 1
            sid = f"s{n:03d}"
            ls = sg["lines"]
            start, end = int(ls[0]["start"]), int(math.ceil(ls[-1]["end"]))
            words = sum(len(ln["text"].split()) for ln in ls)
            body = "\n".join(f"[{fmt_time(ln['start'])}|{int(ln['start'])}] {ln['text']}" for ln in ls)
            head = f"<!-- segment {sid} · {meta['id']} · {fmt_time(start)}–{fmt_time(end)} · {words} words -->\n"
            (segdir / f"{sid}.md").write_text(head + body + "\n", encoding="utf-8")
            out_segs.append({"id": sid, "video": meta["id"], "title": sg["title"], "start": start, "end": end, "words": words,
                             "split": sg["source"], "kind": "content" if words >= MINOR_WORDS else "minor", "lang": lang})
        out_videos.append({k: meta[k] for k in ("id", "yt_id", "title", "channel", "duration", "scope", "upload_date")}
                          | {"transcript": cues["source"], "language": lang, "has_chapters": bool(meta["chapters"])})
    manifest = {"scope": vids["scope"], "videos": out_videos, "segments": out_segs,
                "note": "times are seconds in the video; ids are global and stable for the same input"}
    write_json(work.manifest, manifest)
    return manifest
