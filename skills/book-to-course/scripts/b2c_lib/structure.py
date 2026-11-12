"""Stage 3 — detect chapter/section structure.

Order of preference:
  1. the PDF's own outline (bookmarks)      -> confidence high/medium
  2. heading detection (regex + font size)  -> confidence medium/low
  3. fixed-size page chunks                 -> confidence low (always works)
Output: work/structure.json with `nodes`, each anchored to (page, paragraph index) so that split
can cut the text stream exactly at the heading, even when two chapters share a page.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from .common import Work, norm_for_match, norm_ws, write_json
from .extract import _open
from .paras import body_size, build_paras, load_clean_pages

FRONT_RE = re.compile(
    r"^(contents|table of contents|copyright|title page|dedication|acknowledg|foreword|preface|about the|"
    r"оглавление|содержание|предисловие|от автора|введение к изданию|благодарност|аннотация|посвящение)", re.I)
BACK_RE = re.compile(
    r"^(index|bibliograph|references|glossary|about the author|colophon|notes$|"
    r"предметный указатель|указатель|литература|список литературы|библиография|глоссарий|примечания)", re.I)
CHAPTER_RE = re.compile(r"^(chapter|глава|lecture|лекция)\s+([0-9]+|[ivxlc]+|[а-яё]+)\b", re.I)
PART_RE = re.compile(r"^(part|часть|раздел)\s+([0-9]+|[ivxlc]+|[а-яё]+)\b", re.I)
NUM_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+(\S.*)$")
TOCLINE_RE = re.compile(r"(\.{3,}|\s{2,}|\s)\d{1,4}\s*$")


def kind_of(title: str) -> str:
    t = title.strip()
    if BACK_RE.match(t):
        return "back"
    if FRONT_RE.match(t):
        return "front"
    return "chapter"


# ── anchoring ────────────────────────────────────────────────────────────


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def find_heading(paras: list[dict], title: str, start: int = 0) -> tuple[int, int] | None:
    """Find the paragraph (and how many consecutive paragraphs) that spell `title`."""
    nt = norm_for_match(title)
    if not nt:
        return None
    for i in range(start, len(paras)):
        acc = ""
        for span in range(1, 4):
            if i + span > len(paras):
                break
            acc = norm_for_match(" ".join(p["text"] for p in paras[i:i + span]))
            if not acc:
                break
            head = acc[: len(nt) + 8]
            if acc == nt or _ratio(head, nt) >= 0.82 or (len(acc) >= 4 and nt.startswith(acc) and span == 1 and len(acc) >= 0.5 * len(nt)):
                if len(acc) <= len(nt) + 80 or nt in acc:
                    return i, span
            if len(acc) > len(nt) + 80:
                break
    return None


def _anchor_by_y(paras: list[dict], y: float | None) -> int:
    if y is None:
        return 0
    for i, p in enumerate(paras):
        if p["y0"] and p["y0"] >= y - 3:
            return i
    return 0


# ── 1. outline ───────────────────────────────────────────────────────────


def from_outline(pdf: Path, work: Work, pages: tuple[int, int], paras_by_page: dict[int, list[dict]]):
    doc = _open(pdf)
    try:
        toc = doc.get_toc(simple=False)
    finally:
        doc.close()
    entries = []
    for lvl, title, page, dest in toc:
        if page < 1:
            continue
        y = None
        try:
            to = dest.get("to")
            y = float(to.y) if to is not None else None
        except Exception:
            y = None
        entries.append({"lvl": lvl, "title": norm_ws(title), "page": page, "y": y})
    if not entries:
        return None
    counts: dict[int, int] = {}
    for e in entries:
        counts[e["lvl"]] = counts.get(e["lvl"], 0) + 1
    ch_lvl = next((l for l in sorted(counts) if counts[l] >= 3), None)
    if ch_lvl is None:
        return None
    nodes, part = [], None
    a, b = pages
    for e in entries:
        if e["lvl"] < ch_lvl:
            part = e["title"]
            continue
        if e["lvl"] > ch_lvl + 1:
            continue
        level = 1 if e["lvl"] == ch_lvl else 2
        node = {"level": level, "title": e["title"], "page": e["page"], "part": part,
                "kind": kind_of(e["title"]) if level == 1 else "chapter", "_y": e["y"]}
        nodes.append(node)
    _assign_ids(nodes)  # ids come from the whole-book outline, so they stay stable across scopes
    # keep nodes inside the requested range, remember the chapter that straddles its start
    inside = [n for n in nodes if a <= n["page"] <= b]
    before = [n for n in nodes if n["page"] < a and n["level"] == 1]
    carry = before[-1] if before else None
    # resolve anchors
    out = []
    cursor = (0, 0)
    for n in inside:
        paras = paras_by_page.get(n["page"], [])
        hit = find_heading(paras, n["title"], start=cursor[1] if cursor[0] == n["page"] else 0)
        if hit:
            idx, span = hit
            anchored = True
        else:
            idx, span, anchored = _anchor_by_y(paras, n.pop("_y", None)), 0, False
        n.pop("_y", None)
        n["anchor"] = {"page": n["page"], "para": idx, "span": span, "anchored": anchored}
        cursor = (n["page"], idx + max(span, 1))
        out.append(n)
    if carry is not None:
        first = out[0] if out else None
        stream_start_ok = first is not None and first["anchor"]["page"] == a and first["anchor"]["para"] == 0
        if not stream_start_ok:
            out.insert(0, {"level": 1, "id": carry["id"], "title": carry["title"], "page": a, "part": carry["part"],
                           "kind": carry["kind"], "partial": True,
                           "anchor": {"page": a, "para": 0, "span": 0, "anchored": False}})
    n_ch = [n for n in out if n["level"] == 1]
    anch = [n for n in n_ch if n["anchor"]["anchored"]]
    conf = "high" if n_ch and len(anch) >= 0.8 * len(n_ch) else "medium"
    return {"source": "outline", "confidence": conf, "chapter_outline_level": ch_lvl, "nodes": out}


def _assign_ids(nodes: list[dict]) -> None:
    ci = si = 0
    for n in nodes:
        if n["level"] == 1:
            ci += 1
            si = 0
            n["id"] = f"ch{ci:02d}"
        else:
            si += 1
            n["id"] = f"ch{ci:02d}.s{si}" if ci else f"s{si}"


def outline_chapters(pdf: Path) -> list[dict]:
    """Cheap whole-book chapter list from the PDF outline (no text extraction). [] if unusable."""
    doc = _open(pdf)
    try:
        toc = doc.get_toc(simple=True)
        total = doc.page_count
    finally:
        doc.close()
    counts: dict[int, int] = {}
    for lvl, _t, pg in toc:
        counts[lvl] = counts.get(lvl, 0) + 1
    ch_lvl = next((l for l in sorted(counts) if counts[l] >= 3), None)
    if ch_lvl is None:
        return []
    chs = [(t.strip(), pg) for lvl, t, pg in toc if lvl == ch_lvl and pg > 0]
    out = []
    for i, (t, pg) in enumerate(chs):
        end = chs[i + 1][1] if i + 1 < len(chs) else total
        out.append({"id": f"ch{i + 1:02d}", "title": t, "page_start": pg, "page_end": max(pg, end),
                    "kind": kind_of(t)})
    return out


# ── 2. headings ──────────────────────────────────────────────────────────


def _is_tocish(paras: list[dict]) -> bool:
    return sum(1 for p in paras if p["nl"] == 1 and TOCLINE_RE.search(p["text"])) >= 5


def from_headings(work: Work, pages: tuple[int, int], pages_clean: list[dict],
                  paras_by_page: dict[int, list[dict]]):
    body = body_size(pages_clean)
    ocr_only = body == 0
    cand = []  # (page, para_idx, span, kind, depth, title, size)
    for pg in pages_clean:
        paras = paras_by_page[pg["page"]]
        if _is_tocish(paras):
            continue
        i = 0
        while i < len(paras):
            p = paras[i]
            text, words = p["text"], len(p["text"].split())
            head_like = (p["nl"] <= 2 and words <= 14 and not text.rstrip().endswith((".", ",", ";"))) or \
                (words <= 3 and CHAPTER_RE.match(text))
            big = ocr_only or p["size"] >= body * 1.08 or p["bold"]
            m_ch = CHAPTER_RE.match(text)
            m_part = PART_RE.match(text)
            m_num = NUM_RE.match(text)
            span, title = 1, text
            if (m_ch or m_part) and head_like and big:
                if words <= 3 and i + 1 < len(paras):
                    nxt = paras[i + 1]
                    if len(nxt["text"].split()) <= 14 and nxt["nl"] <= 2:
                        title, span = f"{text}. {nxt['text']}", 2
                cand.append((pg["page"], i, span, "part" if m_part and not m_ch else "A", 1, title, p["size"]))
            elif m_num and head_like and big and (p["size"] >= body * 1.08 or p["bold"] or ocr_only):
                depth = m_num.group(1).count(".") + 1
                cand.append((pg["page"], i, 1, "B", depth, text, p["size"]))
            elif not ocr_only and p["size"] >= body * 1.35 and head_like and not text.isdigit() and words >= 1:
                cand.append((pg["page"], i, 1, "C", 0, text, p["size"]))
            i += span if span > 1 else 1
    A = [c for c in cand if c[3] == "A"]
    B1 = [c for c in cand if c[3] == "B" and c[4] == 1]
    B2 = [c for c in cand if c[3] == "B" and c[4] == 2]
    C = [c for c in cand if c[3] == "C"]
    chapters, sections = [], []
    if len(A) >= 2:
        chapters, sections = A, B2
    elif len(B1) >= 2:
        chapters, sections = B1, B2
    elif C:
        sizes = sorted({c[6] for c in C}, reverse=True)
        top = [c for c in C if c[6] == sizes[0]]
        if len(top) >= 2:
            chapters = top
            if len(sizes) > 1:
                sections = [c for c in C if c[6] == sizes[1]]
    if len(chapters) < 2:
        return None
    nodes = []
    for lvl, group in ((1, chapters), (2, sections)):
        for (pno, pi, span, _k, _d, title, _s) in group:
            nodes.append({"level": lvl, "title": norm_ws(title), "page": pno, "part": None,
                          "kind": kind_of(title) if lvl == 1 else "chapter",
                          "anchor": {"page": pno, "para": pi, "span": span, "anchored": True}})
    nodes.sort(key=lambda n: (n["anchor"]["page"], n["anchor"]["para"], n["level"]))
    # preamble before first chapter
    first = nodes[0]
    start_page = pages_clean[0]["page"]
    if not (first["anchor"]["page"] == start_page and first["anchor"]["para"] == 0):
        nodes.insert(0, {"level": 1, "title": "Opening pages", "page": start_page, "part": None, "kind": "front",
                         "anchor": {"page": start_page, "para": 0, "span": 0, "anchored": False}})
    conf = "medium" if len([n for n in nodes if n["level"] == 1]) >= 3 else "low"
    return {"source": "headings", "confidence": conf, "body_size": body, "nodes": nodes}


# ── 3. chunks ────────────────────────────────────────────────────────────


def from_chunks(pages: tuple[int, int], chunk: int):
    a, b = pages
    nodes = []
    for s in range(a, b + 1, chunk):
        e = min(b, s + chunk - 1)
        nodes.append({"level": 1, "title": f"Pages {s}–{e}", "page": s, "part": None, "kind": "chapter",
                      "anchor": {"page": s, "para": 0, "span": 0, "anchored": False}})
    return {"source": "chunks", "confidence": "low", "nodes": nodes}


# ── driver ───────────────────────────────────────────────────────────────


def detect(pdf: Path, work: Work, pages: tuple[int, int], mode: str = "auto", chunk_pages: int = 20) -> dict:
    pages_clean = load_clean_pages(work, *pages)
    paras_by_page = {pg["page"]: build_paras(pg["lines"]) for pg in pages_clean}
    result = None
    if mode in ("auto", "outline"):
        result = from_outline(pdf, work, pages, paras_by_page)
    if result is None and mode in ("auto", "headings"):
        result = from_headings(work, pages, pages_clean, paras_by_page)
    if result is None:
        result = from_chunks(pages, chunk_pages)
    if any("id" not in n for n in result["nodes"]):
        _assign_ids(result["nodes"])
    result["pages"] = list(pages)
    result["tried"] = mode
    write_json(work.structure, result)
    return result
