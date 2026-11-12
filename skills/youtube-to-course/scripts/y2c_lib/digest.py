"""Stage 5 — cheap local digests (TF-IDF + TextRank-lite), no LLM. Output: work/digest_all.md (Pass-1 input).

Per segment: 2-3 key sentences (with timestamps), distinctive terms, definition-like sentences, numbers, names,
and — for auto/whisper transcripts — 'check' words that look like mis-hearings of words in the title/description/chapters.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from difflib import get_close_matches

from .common import Work, est_tokens, fmt_time, read_json, sentences, tokens, truncate_words, yt_link

DEF = re.compile(r"\b(?:(?:is|are) (?:a|an|the|called|defined as|when|what)|means|refers to|stands for|(?:это|называется|называют|означает))\b", re.I)
NUM = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:%|percent|ms|s|sec|seconds|minutes|hours|x|k|m|gb|mb|kb|hz|khz|mhz|ghz|km|cm|mm|kg|°c|ev|процент\w*|секунд\w*|раз)?", re.I)
NAME = re.compile(r"\b([A-ZА-Я][\w-]{2,}(?:\s[A-ZА-Я][\w-]{2,})?)\b")


def read_segment(work: Work, sid: str) -> list[dict]:
    """[{t, text}] from work/segments/sNNN.md"""
    out = []
    for ln in (work.root / "segments" / f"{sid}.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\[[\d:]+\|(\d+)\] (.*)", ln)
        if m:
            out.append({"t": int(m.group(1)), "text": m.group(2)})
    return out


def _sents(lines: list[dict]) -> list[dict]:
    """sentences with the time of the line they start in"""
    text, marks = "", []
    for ln in lines:
        marks.append((len(text), ln["t"]))
        text += ln["text"] + " "
    if len(re.findall(r"[.!?…]\s", text)) < len(lines) / 4:   # auto-captions / Whisper without punctuation: one line = one unit
        return [{"t": ln["t"], "text": ln["text"]} for ln in lines]
    out, pos = [], 0
    for s in sentences(text):
        i = text.find(s, pos)
        pos = i + len(s)
        t = max((tm for off, tm in marks if off <= i), default=lines[0]["t"])
        out.append({"t": t, "text": s})
    return out


def _idf(all_docs: list[list[str]]) -> tuple[dict[str, float], float]:
    df: Counter = Counter()
    for d in all_docs:
        df.update(set(d))
    n = len(all_docs)
    return {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}, math.log(n + 1)


def _textrank(vecs: list[Counter], iters: int = 25, d: float = 0.85) -> list[float]:
    n = len(vecs)
    norm = [math.sqrt(sum(v * v for v in x.values())) or 1.0 for x in vecs]
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dot = sum(v * vecs[j].get(k, 0) for k, v in vecs[i].items())
            sim[i][j] = sim[j][i] = dot / (norm[i] * norm[j])
    rank = [1.0 / n] * n
    for _ in range(iters):
        rank = [(1 - d) / n + d * sum(sim[j][i] / (sum(sim[j]) or 1) * rank[j] for j in range(n) if j != i) for i in range(n)]
    return rank


def digest_segment(seg: dict, lines: list[dict], idf: dict[str, float], default_idf: float, vocab: list[str], vid_id: str,
                   check_misheard: bool) -> str:
    lang = seg["lang"]
    screen = [ln for ln in lines if ln["text"].startswith("[on-screen]")]
    lines = [ln for ln in lines if not ln["text"].startswith("[on-screen]")] or lines
    sents = [s for s in _sents(lines) if 5 <= len(s["text"].split()) <= 60]
    toks = [tokens(s["text"], lang) for s in sents]
    vecs = [Counter({t: c * idf.get(t, default_idf) for t, c in Counter(tk).items()}) for tk in toks]
    picks: list[dict] = []
    if sents:
        rank = _textrank(vecs) if len(sents) <= 120 else [sum(v.values()) for v in vecs]
        scored = sorted(range(len(sents)), key=lambda i: (-(rank[i] * (1.15 if i < 2 else 1.0)), i))
        picks = [sents[i] for i in sorted(scored[:3])]
    tf = Counter(t for tk in toks for t in tk)
    tf = Counter({t: c for t, c in tf.items() if "'" not in t and "’" not in t})
    terms = [t for t in sorted(tf, key=lambda t: (-tf[t] * idf.get(t, default_idf), t)) if tf[t] >= 2][:8]
    defs = [s for s in sents if DEF.search(s["text"]) and 6 <= len(s["text"].split()) <= 35][:2]
    text = " ".join(s["text"] for s in sents)
    nums = list(dict.fromkeys(m.group(0).strip() for m in NUM.finditer(text) if re.search(r"\d", m.group(0)) and len(m.group(0).strip()) > 1))[:6]
    # proper names: capitalised words that are NOT the first word of a sentence
    mid = " ".join(" ".join(s["text"].split()[1:]) for s in sents)
    names = [n for n, c in Counter(NAME.findall(mid)).most_common(8) if n.lower() not in {t for t in terms}][:6]
    out = [f"### {seg['id']} · {fmt_time(seg['start'])}–{fmt_time(seg['end'])} · {seg['words']} words · {seg['title']}"]
    out += [f"- key [{fmt_time(s['t'])}]: {truncate_words(s['text'], 28)}" for s in picks]
    out += [f"- on-screen [{fmt_time(ln['t'])}]: {truncate_words(ln['text'][len('[on-screen]'):].strip(), 18)}" for ln in screen[:3]]
    if terms:
        out.append("- terms: " + ", ".join(terms))
    out += [f"- def [{fmt_time(s['t'])}]: {truncate_words(s['text'], 28)}" for s in defs]
    if nums:
        out.append("- numbers: " + ", ".join(nums))
    if names:
        out.append("- names: " + ", ".join(names))
    if check_misheard and vocab:
        words = Counter(w for w in re.findall(r"[^\W\d_]{4,}", text.lower()))
        sus = []
        vocab_l = [v.lower() for v in vocab]
        for w in words:
            if w in vocab_l:
                continue
            m = get_close_matches(w, vocab_l, n=1, cutoff=0.8)
            if m:
                sus.append(f"{w}→{m[0]}")
        if sus:
            out.append("- check (maybe mis-heard): " + ", ".join(sorted(sus)[:6]))
    return "\n".join(out)


def vocab_from_meta(meta: dict) -> list[str]:
    """Words the creator typed (title, description, chapter titles): ground truth for technical spellings."""
    text = " ".join([meta["title"], meta.get("description", "")] + [c["title"] for c in meta["chapters"]])
    return sorted({w for w in re.findall(r"[^\W\d_][\w-]{3,}", text) if len(w) >= 5})


def digest_all(work: Work) -> dict:
    manifest = read_json(work.manifest)
    vids = {v["id"]: v for v in read_json(work.videos)["videos"]}
    seg_lines = {s["id"]: read_segment(work, s["id"]) for s in manifest["segments"]}
    docs = [tokens(" ".join(ln["text"] for ln in ls), s["lang"]) for s, ls in ((s, seg_lines[s["id"]]) for s in manifest["segments"])]
    idf, dflt = _idf(docs)
    parts = ["# Digest (generated by scripts; read this, not the transcripts, for Pass 1)\n"]
    for v in manifest["videos"]:
        meta = vids[v["id"]]
        parts.append(f"\n## {v['id']} · {v['title']} · {fmt_time(v['duration'])} · {v['channel']} · transcript={v['transcript']}"
                     f" · scope {fmt_time(v['scope'][0])}–{fmt_time(v['scope'][1])} · {yt_link(v['yt_id'], 0)}")
        desc = " ".join((meta.get("description") or "").split())[:300]
        if desc:
            parts.append(f"description: {desc}")
        vocab = vocab_from_meta(meta)
        for s in (s for s in manifest["segments"] if s["video"] == v["id"]):
            if s["kind"] == "minor":
                parts.append(f"### {s['id']} · {fmt_time(s['start'])}–{fmt_time(s['end'])} · {s['words']} words · {s['title']} (minor: not required)")
                continue
            parts.append(digest_segment(s, seg_lines[s["id"]], idf, dflt, vocab, v["yt_id"], v["transcript"] != "manual"))
    text = "\n".join(parts) + "\n"
    work.digest.write_text(text, encoding="utf-8")
    return {"digest_tokens_est": est_tokens(text), "segments": len(manifest["segments"])}
