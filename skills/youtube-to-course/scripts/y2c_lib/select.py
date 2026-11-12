"""Stage 6 — Pass-2 packs: the transcript text a lesson needs, in time order, within a token budget.

If the lesson's segments fit the budget the pack is complete. Otherwise sentences are ranked by TF-IDF (+ the outline's
keywords) per segment, the best are kept in time order and gaps are marked `[… omitted N words …]`.
`needs_more=True` in the header when more than 45% of the words were dropped: read the gaps with `read`.
"""
from __future__ import annotations

import math
from collections import Counter

from .common import Work, est_tokens, fmt_time, log_usage, read_json, tokens
from .digest import _sents, read_segment


def _lesson(outline: dict, lid: str) -> dict:
    for m in outline["modules"]:
        for lsn in m["lessons"]:
            if lsn["id"] == lid:
                return lsn
    raise SystemExit(f"lesson {lid} not in outline")


def lesson_segments(lesson: dict) -> list[str]:
    return [r["segment"] for r in lesson["source_refs"]]


def pack(work: Work, lid: str, budget: int = 2500) -> dict:
    outline, manifest = read_json(work.outline), read_json(work.manifest)
    seg = {s["id"]: s for s in manifest["segments"]}
    vids = {v["id"]: v for v in manifest["videos"]}
    lesson = _lesson(outline, lid)
    sids = sorted(set(lesson_segments(lesson)), key=lambda x: seg[x]["start"] if x in seg else 0)
    bad = [s for s in sids if s not in seg]
    if bad:
        raise SystemExit(f"unknown segments {bad}")
    kw = {w.lower() for r in lesson["source_refs"] for w in r.get("keywords", [])}
    total_words = sum(seg[s]["words"] for s in sids)
    full = est_tokens(" ".join(" ".join(ln["text"] for ln in read_segment(work, s)) for s in sids)) <= budget
    body, kept_words = [], 0
    for sid in sids:
        s = seg[sid]
        v = vids[s["video"]]
        body.append(f"<!-- {sid} · {s['video']} · {fmt_time(s['start'])}–{fmt_time(s['end'])} · {s['title']} · "
                    f"https://youtu.be/{v['yt_id']} -->")
        lines = read_segment(work, sid)
        if full:
            for ln in lines:
                body.append(f"[{fmt_time(ln['t'])}|{ln['t']}] {ln['text']}")
            kept_words += s["words"]
            continue
        sents = _sents(lines)
        toks = [tokens(x["text"], s["lang"]) for x in sents]
        df: Counter = Counter()
        for tk in toks:
            df.update(set(tk))
        n = len(sents) + 1
        score = [sum(math.log(n / (df[t] + 0.5)) * (3 if t in kw or any(k in t for k in kw) else 1) for t in tk) / (len(tk) ** 0.5 or 1)
                 for tk in toks]
        share = max(150, int(budget * 3.2 * s["words"] / max(total_words, 1)))  # words allowed for this segment
        chosen, used = set(), 0
        for i in sorted(range(len(sents)), key=lambda i: (-score[i], i)):
            w = len(sents[i]["text"].split())
            if used + w > share:
                continue
            chosen.add(i)
            used += w
        gap = 0
        for i, x in enumerate(sents):
            if i in chosen:
                if gap:
                    body.append(f"[… omitted {gap} words …]")
                    gap = 0
                body.append(f"[{fmt_time(x['t'])}|{x['t']}] {x['text']}")
            else:
                gap += len(x["text"].split())
        if gap:
            body.append(f"[… omitted {gap} words …]")
        kept_words += used
    needs_more = (not full) and kept_words < 0.55 * total_words
    head = (f"<!-- pack {lid} · segments {', '.join(sids)} · complete={full} · words {kept_words}/{total_words} · needs_more={needs_more} -->\n"
            f"<!-- objectives: {' | '.join(lesson['objectives'])} -->\n")
    text = head + "\n".join(body) + "\n"
    work.selections.mkdir(parents=True, exist_ok=True)
    (work.selections / f"{lid}.md").write_text(text, encoding="utf-8")
    log_usage(work, "select", lid, text)
    return {"lesson": lid, "tokens_est": est_tokens(text), "complete": full, "needs_more": needs_more, "words": f"{kept_words}/{total_words}"}


def read_range(work: Work, sid: str, a: int | None, b: int | None, max_tokens: int = 4000) -> str:
    """Explicit fallback: the exact transcript lines of a segment between a and b seconds (logged)."""
    lines = [ln for ln in read_segment(work, sid) if (a is None or ln["t"] >= a) and (b is None or ln["t"] <= b)]
    out, used = [], 0
    for ln in lines:
        row = f"[{fmt_time(ln['t'])}|{ln['t']}] {ln['text']}"
        used += est_tokens(row)
        if used > max_tokens:
            out.append("[… truncated by --max-tokens …]")
            break
        out.append(row)
    text = "\n".join(out)
    log_usage(work, "read_full", f"{sid}:{a}-{b}", text)
    return text
