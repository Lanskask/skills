"""Stage 5 — cheap local chapter digests (no LLM).

Per chapter: section list, opening/closing paragraph, TextRank key sentences (TF-IDF cosine graph,
book-wide IDF), definition sentences, bold/italic terms, TF-IDF keywords, figure/table captions.
Each digest is capped at a token budget (default 450). Also writes work/digest_all.md, the single file
the LLM reads in Pass 1.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from .common import Work, est_tokens, read_json, sentences, tokens, truncate_words

DEF_EN = re.compile(
    r"\b(is|are|was|were)\s+(defined|called|termed|known|referred to)\b|\bwe\s+(define|call|denote|refer to)\b"
    r"|\bdenotes?\b|\bstands?\s+for\b|\bis\s+the\s+(process|study|ability|measure)\s+of\b", re.I)
DEF_RU = re.compile(
    r"\bназывается\b|\bназывают\b|\bопределяется\s+как\b|\bбудем\s+называть\b|\bобозначает\b|\bопределим\b"
    r"|\bпод\s+\S+(\s+\S+)?\s+(понимается|понимают)\b|\s[—–-]\s+это\s", re.I)


def _surface_forms(texts: list[str], lang: str) -> dict[str, str]:
    """Map stem -> most frequent surface word (for readable keywords)."""
    from .common import _WORD, stem

    c: dict[str, Counter] = defaultdict(Counter)
    for t in texts:
        for w in _WORD.findall(t.lower()):
            c[stem(w, lang)][w] += 1
    return {s: max(forms.items(), key=lambda kv: (kv[1], -len(kv[0]), kv[0]))[0] for s, forms in c.items()}


def _chapter_sentences(paras: list[dict]) -> list[dict]:
    out = []
    for p in paras:
        if p["kind"] != "p" or p.get("eq"):
            continue
        for s in sentences(p["text"]):
            n = len(s.split())
            letters = sum(c.isalpha() for c in s)
            if 6 <= n <= 60 and letters >= 0.6 * len(s):
                out.append({"text": s, "page": p["page"], "para": p["i"]})
    return out


def textrank(vecs: list[dict[str, float]], iters: int = 30, d: float = 0.85) -> list[float]:
    n = len(vecs)
    if n == 0:
        return []
    norms = [math.sqrt(sum(v * v for v in vec.values())) or 1.0 for vec in vecs]
    inv: dict[str, list[int]] = defaultdict(list)
    for i, vec in enumerate(vecs):
        for t in vec:
            inv[t].append(i)
    weights: list[dict[int, float]] = [defaultdict(float) for _ in range(n)]
    for t, ids in inv.items():
        if len(ids) < 2 or len(ids) > max(30, n // 4):  # ultra-common terms add cost, not signal
            continue
        for a in range(len(ids)):
            i = ids[a]
            for b in range(a + 1, len(ids)):
                j = ids[b]
                w = vecs[i][t] * vecs[j][t]
                weights[i][j] += w
                weights[j][i] += w
    sim = [{j: w / (norms[i] * norms[j]) for j, w in row.items()} for i, row in enumerate(weights)]
    out_sum = [sum(r.values()) or 1.0 for r in sim]
    score = [1.0 / n] * n
    for _ in range(iters):
        new = [(1 - d) / n] * n
        for i in range(n):
            share = score[i] / out_sum[i]
            for j, w in sim[i].items():
                new[j] += d * w * share
        score = new
    return score


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(t, 0.0) for t, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def build_idf(work: Work, chapters: list[dict], lang: str) -> dict[str, float]:
    df: Counter = Counter()
    docs = 0
    for c in chapters:
        data = read_json(work.root / c["paras_file"])
        toks = set()
        for p in data["paras"]:
            if p["kind"] == "p":
                toks.update(tokens(p["text"], lang))
        df.update(toks)
        docs += 1
    n = max(docs, 1)
    return {t: math.log((1 + n) / (1 + f)) + 1.0 for t, f in df.items()}


def digest_chapter(work: Work, ch: dict, idf: dict[str, float], lang: str, budget: int) -> str:
    data = read_json(work.root / ch["paras_file"])
    paras = data["paras"]
    body = [p for p in paras if p["kind"] == "p"]
    sents = _chapter_sentences(paras)
    default_idf = max(idf.values(), default=1.0)
    vecs = []
    for s in sents:
        tf = Counter(tokens(s["text"], lang))
        vecs.append({t: c * idf.get(t, default_idf) for t, c in tf.items()})
    scores = textrank(vecs)
    order = sorted(range(len(sents)), key=lambda i: (-scores[i], i))

    picked: list[int] = []
    for i in order:
        if all(_cos(vecs[i], vecs[j]) < 0.55 for j in picked):
            picked.append(i)
        if len(picked) >= 8:
            break

    # keywords by chapter tf-idf
    ctf: Counter = Counter()
    for p in body:
        ctf.update(tokens(p["text"], lang))
    kw_stems = [t for t, _ in sorted(ctf.items(), key=lambda kv: (-kv[1] * idf.get(kv[0], default_idf), kv[0]))
                if ctf[t] >= 2][:10]
    surf = _surface_forms([p["text"] for p in body], lang)
    keywords = [surf.get(t, t) for t in kw_stems]

    # bold / italic terms
    tc: Counter = Counter()
    first_seen: dict[str, int] = {}
    canon: dict[str, str] = {}
    for p in paras:
        if p["kind"] != "p":
            continue
        for t in p["bt"] + p["it"]:
            t2 = re.sub(r"[\s.,;:]+$", "", t.strip())
            key = t2.lower()
            if len(key) < 3 or key.isdigit():
                continue
            tc[key] += 1
            first_seen.setdefault(key, len(first_seen))
            canon.setdefault(key, t2)
    terms = [canon[k] for k, _ in sorted(tc.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))][:12]

    defre = DEF_RU if lang == "ru" else DEF_EN
    defs = [s for s in _all_sentences(paras) if defre.search(s["text"]) and 5 <= len(s["text"].split()) <= 60][:5]
    caps = [p for p in paras if p["kind"] == "cap"]
    n_fig = sum(1 for p in caps if re.match(r"^(fig|рис)", p["text"], re.I))
    n_tab = sum(1 for p in caps if re.match(r"^(tab|табл)", p["text"], re.I))
    n_eq = sum(1 for p in paras if p.get("eq"))
    h2 = [p for p in paras if p["kind"] == "h2"]
    h3 = [p for p in paras if p["kind"] == "h3"]

    def render(k: int, nd: int, tw: int) -> str:
        L = [f"### {ch['id']} — {ch['title']}  (pp. {ch['page_start']}–{ch['page_end']}, "
             f"{ch['words']:,} words, ~{ch['est_tokens']:,} tok)"]
        if h2:
            L.append("Sections: " + " · ".join(f"{h['text']} (p.{h['page']})" for h in h2[:12]))
        if h3 and not h2:
            L.append("Headings: " + " · ".join(f"{h['text']} (p.{h['page']})" for h in h3[:10]))
        if body:
            L.append(f"Opening (p.{body[0]['page']}): {truncate_words(body[0]['text'], tw)}")
        if k:
            L.append("Key sentences:")
            for i in sorted(picked[:k], key=lambda i: (sents[i]["page"], sents[i]["para"])):
                L.append(f"- [p.{sents[i]['page']}] {truncate_words(sents[i]['text'], 38)}")
        if nd and defs:
            L.append("Definitions:")
            for s in defs[:nd]:
                L.append(f"- [p.{s['page']}] {truncate_words(s['text'], 38)}")
        if terms:
            L.append("Terms (bold/italic): " + "; ".join(terms))
        if keywords:
            L.append("Keywords (tf-idf): " + ", ".join(keywords))
        if caps:
            L.append("Captions: " + " | ".join(f"[{p.get('id', '')} p.{p['page']}] {truncate_words(p['text'], 18)}" for p in caps[:4]))
        if len(body) > 1:
            L.append(f"Closing (p.{body[-1].get('page_end', body[-1]['page'])}): {truncate_words(body[-1]['text'], max(25, tw - 10))}")
        if n_eq:
            key = [p for p in paras if p.get("eq") and p.get("num")] or [p for p in paras if p.get("eq")]
            L.append(f"Equations: {n_eq} display ({sum(1 for p in paras if p.get('num'))} numbered). Key: "
                     + "; ".join(f"{('(' + p['num'] + ') ') if p.get('num') else ''}{p['id']} p.{p['page']}" for p in key[:5]))
        L.append(f"Stats: figures {n_fig}, tables {n_tab}, equations {n_eq}, sections {len(h2)}")
        return "\n".join(L)

    k, nd, tw = min(6, len(picked)), min(4, len(defs)), 55
    text = render(k, nd, tw)
    while est_tokens(text) > budget and (k > 2 or nd > 0 or tw > 25):
        if k > 3:
            k -= 1
        elif nd > 1:
            nd -= 1
        elif tw > 25:
            tw -= 10
        elif k > 2:
            k -= 1
        else:
            nd = 0
            tw = 20
            break
        text = render(k, nd, tw)
    return text + "\n"


def _all_sentences(paras: list[dict]) -> list[dict]:
    out = []
    for p in paras:
        if p["kind"] == "p":
            for s in sentences(p["text"]):
                out.append({"text": s, "page": p["page"]})
    return out


def digest_all(work: Work, budget: int = 450) -> dict:
    work.digests.mkdir(parents=True, exist_ok=True)
    manifest = read_json(work.manifest)
    lang = manifest["book"]["lang"]
    chapters = [c for c in manifest["chapters"] if c["kind"] == "chapter"]
    idf = build_idf(work, chapters, lang)
    parts, total = [], 0
    toc = []
    for c in manifest["chapters"]:
        flag = "" if c["kind"] == "chapter" else f" [{c['kind']}: skipped]"
        toc.append(f"- {c['id']}  {c['title']}  pp.{c['page_start']}–{c['page_end']}  "
                   f"{c['words']:,}w{flag}")
    for c in chapters:
        d = digest_chapter(work, c, idf, lang, budget)
        (work.digests / f"{c['id']}.md").write_text(d, encoding="utf-8")
        parts.append(d)
        total += est_tokens(d)
    b = manifest["book"]
    head = (f"# Digest of: {b['title']}\n"
            f"Language: {b['lang']} · structure: {manifest['structure']['source']} "
            f"({manifest['structure']['confidence']}) · scope pages {manifest['scope']['pages'][0]}–"
            f"{manifest['scope']['pages'][1]}\nCitations use PDF page numbers (p.N).\n\n## Table of contents\n"
            + "\n".join(toc) + "\n\n## Chapter digests\n\n")
    full = head + "\n".join(parts)
    (work.root / "digest_all.md").write_text(full, encoding="utf-8")
    return {"chapters": len(chapters), "digest_tokens": total, "digest_all_tokens": est_tokens(full)}
