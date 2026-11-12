"""Stage 6 — per-lesson passage packs (Pass 2 input) and explicit full-text reads.

`select_lesson` picks paragraphs from the chapters a lesson cites, ranked by overlap with the lesson's
title / objectives / keywords (book-wide IDF), under a token budget. Output keeps document order and page
markers, and says honestly when coverage looks thin (`needs_more`).
"""
from __future__ import annotations

import math
import re

from .paras import fmt_code, fmt_eq
from .common import Work, est_tokens, log_usage, read_json, sentences, tokens, truncate_words, write_json
from .digest import DEF_EN, DEF_RU, build_idf


def find_lesson(outline: dict, lesson_id: str) -> tuple[dict, dict]:
    for m in outline.get("modules", []):
        for l in m.get("lessons", []):
            if l["id"] == lesson_id:
                return m, l
    raise KeyError(f"lesson {lesson_id!r} not in outline")


def _condense(text: str, qset: set[str], lang: str, max_words: int) -> str:
    if len(text.split()) <= max_words:
        return text
    sents = sentences(text)
    scored = sorted(range(len(sents)), key=lambda i: (-len(qset & set(tokens(sents[i], lang))), i))
    keep, used = set(), 0
    if sents:
        keep.add(0)
        used = len(sents[0].split())
    for i in scored:
        w = len(sents[i].split())
        if i not in keep and used + w <= max_words:
            keep.add(i)
            used += w
    return " ".join(sents[i] for i in sorted(keep)) + " […]"


def _gap_hint(paras: list[dict], idf: dict[str, float], default_idf: float, lang: str) -> str:
    """Pages and the most distinctive words of omitted paragraphs, so a gap says what is missing (e.g. 'p.5: mersenne, twister')."""
    from collections import Counter

    c: Counter = Counter()
    for p in paras:
        c.update(tokens(p["text"], lang))
    top = [w for w, _ in sorted(c.items(), key=lambda kv: (-kv[1] * idf.get(kv[0], default_idf), kv[0]))[:4]]
    pg = sorted({p["page"] for p in paras})
    return f"p.{pg[0]}" + (f"-{pg[-1]}" if pg[-1] != pg[0] else "") + ": " + ", ".join(top)


def select_lesson(work: Work, lesson_id: str, budget: int = 1800) -> dict:
    manifest = read_json(work.manifest)
    outline = read_json(work.outline)
    lang = manifest["book"]["lang"]
    module, lesson = find_lesson(outline, lesson_id)
    chap_by_id = {c["id"]: c for c in manifest["chapters"]}
    chapters = [c for c in manifest["chapters"] if c["kind"] == "chapter"]
    idf = build_idf(work, chapters, lang)
    default_idf = max(idf.values(), default=1.0)

    qtext = " ".join([lesson["title"], *lesson.get("objectives", [])])
    for ref in lesson["source_refs"]:
        qtext += " " + " ".join(ref.get("keywords", []))
    qset = set(tokens(qtext, lang))
    defre = DEF_RU if lang == "ru" else DEF_EN

    cand = []  # (chapter id, para dict, score)
    for ref in lesson["source_refs"]:
        c = chap_by_id[ref["chapter"]]
        pg = ref.get("pages")
        data = read_json(work.root / c["paras_file"])
        after_h2 = False
        for p in data["paras"]:
            if pg and not (pg[0] <= p["page"] <= pg[1]):
                continue
            if p["kind"] == "h2":
                after_h2 = True
                cand.append({"ch": c["id"], "p": p, "score": 0.0, "first": False})
                continue
            if p["kind"] == "h3":
                cand.append({"ch": c["id"], "p": p, "score": 0.0, "first": False})
                continue
            toks = set(tokens(p["text"], lang))
            overlap = qset & toks
            s = sum(idf.get(t, default_idf) for t in overlap)
            s /= max(len(toks), 8) ** 0.3
            if defre.search(p["text"]):
                s *= 1.25
            cand.append({"ch": c["id"], "p": p, "score": s, "first": after_h2 and p["kind"] == "p"})
            after_h2 = False
    for x in cand:
        if x["p"].get("eq") or x["p"]["kind"] == "code":
            x["score"] = 0.0  # equations and code ride along with the prose around them, below
    paras = [x for x in cand if x["p"]["kind"] in ("p", "cap") and not x["p"].get("eq")]
    if not paras:
        raise ValueError(f"lesson {lesson_id}: no source paragraphs (check source_refs pages)")

    chosen: set[int] = set()
    used = 0
    idx_of = {id(x): i for i, x in enumerate(cand)}

    def cost(x) -> int:
        return est_tokens(_condense(x["p"]["text"], qset, lang, 160)) + 6

    # 0) small source: when everything the lesson cites fits (<= 1.35 x budget), the pack is the complete text (no gaps, no ranking)
    whole = sum(est_tokens(x["p"]["text"]) + 6 for x in paras) <= 1.35 * budget
    if whole:
        for x in paras:
            chosen.add(idx_of[id(x)])
        used = sum(est_tokens(x["p"]["text"]) + 6 for x in paras)
    # 1) structural coverage: opening paragraph of each section, up to 25% of the budget
    for x in ([] if whole else cand):
        if x["first"] and used + cost(x) <= budget * 0.25:
            chosen.add(idx_of[id(x)])
            used += cost(x)
    has_eq = any(x["p"].get("eq") for x in cand)
    has_code = any(x["p"]["kind"] == "code" for x in cand)
    prose_budget = budget * (1 - 0.2 * has_eq - 0.15 * has_code)  # equations 20%, code listings 15%
    # 2) relevance
    for x in ([] if whole else sorted(paras, key=lambda x: (-x["score"], idx_of[id(x)]))):
        i = idx_of[id(x)]
        if i in chosen or x["score"] <= 0:
            continue
        c = cost(x)
        if used + c <= prose_budget:
            chosen.add(i)
            used += c
    # 2b) equations next to chosen prose, or whose number the chosen prose cites; own budget (20% of the pack)
    eq_used, eq_ids = 0, []
    cited_nums = set()
    for i in chosen:
        for m in re.finditer(r"(?:eq(?:uation|s)?\.?|уравнени\w+|формул\w+)\s*\(?(\d+(?:[.\-]\d+)*[a-z]?)\)?", cand[i]["p"]["text"], re.I):
            cited_nums.add(m.group(1))
        for m in re.finditer(r"\((\d+(?:[.\-]\d+)*[a-z]?)\)", cand[i]["p"]["text"]):
            cited_nums.add(m.group(1))
    for i, x in enumerate(cand):
        p = x["p"]
        if not p.get("eq") or i in chosen or len(eq_ids) >= (30 if whole else 8):
            continue
        near = whole or any(j in chosen and cand[j]["ch"] == x["ch"] and not cand[j]["p"].get("eq") for j in (i - 2, i - 1, i + 1))
        if near or (p.get("num") and p["num"] in cited_nums):
            c = est_tokens(fmt_eq(p)) + 4
            if whole or eq_used + c <= budget * 0.20:
                chosen.add(i)
                eq_used += c
                eq_ids.append(p["id"])
    used += eq_used
    # 2b') code listings next to chosen prose (own 15% budget; every listing when the whole source fits)
    code_used, code_ids = 0, []
    for i, x in enumerate(cand):
        p = x["p"]
        if p["kind"] != "code" or i in chosen or len(code_ids) >= (30 if whole else 6):
            continue
        near = whole or any(j in chosen and cand[j]["ch"] == x["ch"] and cand[j]["p"]["kind"] == "p" for j in (i - 2, i - 1, i + 1))
        c = est_tokens(fmt_code(p)) + 4
        if near and (whole or code_used + c <= budget * 0.15):
            chosen.add(i)
            code_used += c
            code_ids.append(p["id"])
    used += code_used
    # 2c) every figure caption in the lesson's pages (cheap, ~25 tokens each): lets the model pick book figures to show
    fig_ids = []
    for i, x in enumerate(cand):
        p = x["p"]
        if p["kind"] == "cap" and p.get("id") and len(fig_ids) < 6:
            chosen.add(i)
            fig_ids.append(p["id"])
            used += est_tokens(p["text"]) + 8
    # 3) if the lesson matched nothing, fall back to evenly spaced paragraphs so the pack is never empty
    if not chosen:
        step = max(1, len(paras) // 6)
        for x in paras[::step][:6]:
            chosen.add(idx_of[id(x)])
            used += cost(x)

    lines: list[str] = []
    pages_used: set[int] = set()
    last_ch, last_page, last_i = None, None, None
    sel_text = []
    for i, x in enumerate(cand):
        p = x["p"]
        if i not in chosen and p["kind"] not in ("h2",):
            continue
        if p["kind"] == "h2":  # headings only if something under them was chosen
            nxt = [j for j in range(i + 1, len(cand)) if cand[j]["p"]["kind"] == "h2" or j in chosen]
            if not nxt or cand[nxt[0]]["p"]["kind"] == "h2":
                continue
        if x["ch"] != last_ch:
            lines.append(f"\n## {x['ch']} — {chap_by_id[x['ch']]['title']}")
            last_ch, last_page, last_i = x["ch"], None, None
        if last_i is not None and i - last_i > 1:
            om = [cand[j]["p"] for j in range(last_i + 1, i) if cand[j]["p"]["kind"] in ("p", "cap") and not cand[j]["p"].get("eq")]
            if om:
                lines.append(f"[… {len(om)} paragraph(s) omitted ({_gap_hint(om, idf, default_idf, lang)}) …]")
        if p["page"] != last_page:
            lines.append(f"<!-- p.{p['page']} -->")
            last_page = p["page"]
        if p["kind"] == "h2":
            lines.append(f"### {p['text']}")
        elif p["kind"] == "h3":
            lines.append(f"#### {p['text']}")
        elif p.get("eq"):
            lines.append(fmt_eq(p))
        elif p["kind"] == "code":
            lines.append(fmt_code(p))
        elif p["kind"] == "cap" and p.get("id"):
            lines.append(f"[FIG {p['id']} · p.{p['page']}] {p['text']}")
        else:
            t = p["text"] if whole else _condense(p["text"], qset, lang, 160)
            lines.append(t)
            sel_text.append(t)
        pages_used.add(p["page"])
        last_i = i
    body = "\n".join(lines).strip() + "\n"

    got = set()
    sel_tokens = set(tokens(" ".join(sel_text), lang))
    got = qset & sel_tokens
    coverage = len(got) / len(qset) if qset else 1.0
    reasons = []
    if coverage < 0.6:
        reasons.append(f"only {coverage:.0%} of objective/keyword terms appear in the pack")
    if not any(x["score"] > 0 for x in paras):
        reasons.append("no paragraph matched the objectives (check wording or source_refs)")
    if manifest["extraction"]["quality"] == "ocr":
        reasons.append("book was OCR'd: expect recognition errors, verify quotes")
    total_src = sum(est_tokens(x["p"]["text"]) for x in paras)
    meta = {
        "lesson": lesson_id, "module": module["id"], "title": lesson["title"], "budget": budget,
        "tokens": est_tokens(body), "source_tokens_available": total_src,
        "pages": [min(pages_used), max(pages_used)] if pages_used else None,
        "complete": whole, "equations": eq_ids, "code": code_ids, "figures": fig_ids, "term_coverage": round(coverage, 2), "missing_terms": sorted(qset - got)[:12],
        "needs_more": bool(reasons), "reasons": reasons,
        "hint": "if needs_more: run `b2c.py read --chapter CH --pages A-B` for the specific pages you need and note it in sources.read_full",
    }
    header = (f"# Pass-2 pack for {lesson_id}: {lesson['title']}\n"
              f"Objectives:\n" + "\n".join(f"{n}. {o}" for n, o in enumerate(lesson.get("objectives", []))) + "\n"
              f"Pack: ~{meta['tokens']} tok of ~{total_src} available · term coverage {meta['term_coverage']:.0%} · "
              f"needs_more={meta['needs_more']}"
              + (f" ({'; '.join(reasons)})" if reasons else "") + "\n"
              + (f"Book figures on these pages: {', '.join(fig_ids)}. To show one in the lesson use a `figure` block; look at it first: "
                 f"`b2c.py fig --id <id> --image`.\n" if fig_ids else "")
              + ("Complete: this pack is the whole source text of the lesson's pages (nothing omitted).\n" if whole else "")
              + (f"Code listings in pack: {', '.join(code_ids)} (copy lines verbatim into a `code` block).\n" if code_ids else "")
              + (f"Equations in pack: {', '.join(eq_ids)}. LaTeX after `draft:` is machine-built from the PDF text layer "
                 f"(sub/superscripts from font geometry): verify with `b2c.py eq --id <id> --image` before relying on it.\n" if eq_ids else ""))
    out = header + "\n" + body
    work.selections.mkdir(parents=True, exist_ok=True)
    (work.selections / f"{lesson_id}.md").write_text(out, encoding="utf-8")
    write_json(work.selections / f"{lesson_id}.json", meta)
    log_usage(work, "select", lesson_id, out)
    return meta


def read_range(work: Work, chapter: str, pages: tuple[int, int] | None, max_tokens: int = 4000) -> str:
    """Explicit fallback read: full cleaned text of part of a chapter, capped, and logged."""
    manifest = read_json(work.manifest)
    c = next(x for x in manifest["chapters"] if x["id"] == chapter)
    data = read_json(work.root / c["paras_file"])
    lines, last_page, used = [f"## {c['id']} — {c['title']}"], None, 0
    for p in data["paras"]:
        if pages and not (pages[0] <= p["page"] <= pages[1]):
            continue
        if p["page"] != last_page:
            lines.append(f"<!-- p.{p['page']} -->")
            last_page = p["page"]
        t = fmt_eq(p) if p.get("eq") else fmt_code(p) if p["kind"] == "code" else {"h2": "### ", "h3": "#### "}.get(p["kind"], "") + p["text"]
        used += est_tokens(t)
        if used > max_tokens:
            lines.append(f"[… truncated at ~{max_tokens} tokens; narrow --pages …]")
            break
        lines.append(t)
    text = "\n".join(lines) + "\n"
    log_usage(work, "full_read", f"{chapter}:{pages[0] if pages else '*'}-{pages[1] if pages else '*'}", text)
    return text
