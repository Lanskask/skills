"""Stage 4 — cut the cleaned page stream into chapter files + manifest.json.

Per chapter:  chapters/chNN-slug.md      (human/LLM readable, `<!-- p.N -->` page markers)
              chapters/chNN.paras.json   (machine form used by digest/select/validate)
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .mathtex import text_to_tex
from .common import Work, detect_lang, est_tokens, read_json, slugify, write_json
from .paras import body_size, build_paras, code_text, fmt_eq, load_clean_pages

CAPTION_RE = re.compile(r"^(figure|fig\.|table|tab\.|рис\.|рисунок|таблица|табл\.)\s*[\dIVX]+[.:\-–—]?", re.I)
FIG_RE = re.compile(r"^(figure|fig\.|рис\.|рисунок)\s*[\dIVX]", re.I)
_TERMINAL = re.compile(r"[.!?…:;»\")\]]$")
_MATH = re.compile(r"[=∑∫√±≤≥≈≠∂∇∞αβγδεθλμνπρσφψω×·⟨⟩]")


_EQNUM = re.compile(r"\s*[(\[](\d+(?:[.\-]\d+)*[a-z]?)[)\]]\s*$")


def _is_equation(text: str) -> bool:
    if len(text) > 160:
        return False
    return len(_MATH.findall(text)) >= 2 or (text.count("=") >= 1 and len(re.findall(r"[A-Za-z]", text)) < 0.6 * len(text))


def eq_info(s: dict) -> tuple[bool, str, str | None]:
    """Is this paragraph a display equation? -> (is_eq, LaTeX draft, equation number).

    Signals: math fonts / math characters on most of its lines, short, and not prose
    (<= 3 ordinary lowercase words). Falls back to the character heuristic for plain-font PDFs."""
    text = s["text"]
    if s.get("mono"):
        return False, "", None
    prose = len(re.findall(r"[a-zа-яё]{4,}", text.lower()))
    by_font = s.get("ml", 0) > 0 and s["ml"] >= 0.5 * s["nl"] and len(text) <= 220 and s["nl"] <= 5 and prose <= 3
    legacy = prose <= 3 and _is_equation(text) and (len(_MATH.findall(text)) >= 2 or not re.search(r"[A-Za-z_]{3,}\s*=\s*[A-Za-z_]", text))
    if not (by_font or legacy):
        return False, "", None
    num = None
    m = _EQNUM.search(text)
    if m:
        num = m.group(1)
    tex = " ".join(s["tx"]) if s.get("tx") else text_to_tex(text)
    mt = _EQNUM.search(tex)
    if mt:
        tex = tex[:mt.start()]
    return True, tex.strip(), num


def _stream(pages_clean: list[dict]) -> list[dict]:
    items = []
    for pg in pages_clean:
        for i, p in enumerate(build_paras(pg["lines"])):
            items.append({"page": pg["page"], "pi": i, **p})
    return items


def _merge_across_pages(paras: list[dict]) -> list[dict]:
    out: list[dict] = []
    for p in paras:
        prev = out[-1] if out else None
        if (prev and prev["kind"] == "p" and p["kind"] == "p" and not prev.get("eq") and not p.get("eq") and p["page"] == prev.get("page_end", prev["page"]) + 1
                and not _TERMINAL.search(prev["text"]) and p["text"][:1].islower()):
            joined = prev["text"]
            if joined.endswith("-") and len(joined) > 1 and joined[-2].isalpha():
                prev["text"] = joined[:-1] + p["text"]
            else:
                prev["text"] = joined + " " + p["text"]
            prev["page_end"] = p["page"]
            prev["bt"] += p["bt"]
            prev["it"] += p["it"]
        else:
            out.append(p)
    return out


def _merge_code(items: list[dict]) -> list[dict]:
    """Consecutive monospace paragraphs (a listing split by blocks or a page break) become one code item."""
    out: list[dict] = []
    for p in items:
        if out and p["kind"] == "code" and out[-1]["kind"] == "code":
            out[-1]["raw"] += p["raw"]
            out[-1]["page_end"] = p["page"]
        else:
            out.append(p)
    for p in out:
        if p["kind"] == "code":  # indentation is computed over the whole listing, not per fragment
            p["text"] = code_text([tuple(x) for x in p.pop("raw")])
    return out


def _merge_equations(items: list[dict]) -> list[dict]:
    """A display equation printed as several lines/blocks (fraction parts, a derivation) is one equation, not 55 fragments."""
    out: list[dict] = []
    for p in items:
        prev = out[-1] if out else None
        if (prev and prev.get("eq") and p.get("eq") and prev["page"] == p["page"] and prev.get("bbox") and p.get("bbox")
                and p["bbox"][1] - prev["bbox"][3] <= 16 and p["bbox"][1] >= prev["bbox"][1] - 2):
            prev["text"] += " " + p["text"]
            prev["tex"] = (prev["tex"] + r" \\ " + p["tex"]).strip()
            prev["num"] = p.get("num") or prev.get("num")
            b0, b1 = prev["bbox"], p["bbox"]
            prev["bbox"] = [min(b0[0], b1[0]), b0[1], max(b0[2], b1[2]), max(b0[3], b1[3])]
            prev["parts"] = prev.get("parts", 1) + 1
        else:
            out.append(p)
    return out


def split(pdf: Path, work: Work, pages: tuple[int, int], extraction: dict,
          chapter_ids: set[str] | None = None) -> dict:
    structure = read_json(work.structure)
    pages_clean = load_clean_pages(work, *pages)
    body = body_size(pages_clean)
    stream = _stream(pages_clean)
    index = {(s["page"], s["pi"]): k for k, s in enumerate(stream)}

    def pos(n: dict) -> int:
        a = n["anchor"]
        k = index.get((a["page"], a["para"]))
        if k is None:  # anchor page had no paragraphs: first item at/after that page
            k = next((j for j, s in enumerate(stream) if s["page"] >= a["page"]), len(stream))
        return k

    nodes = sorted(structure["nodes"], key=lambda n: (pos(n), n["level"]))
    chapters: list[dict] = []
    cur = None
    for n in nodes:
        k = pos(n)
        if n["level"] == 1:
            cur = {"node": n, "start": k, "head_span": n["anchor"]["span"], "sections": []}
            chapters.append(cur)
        elif cur is not None:
            cur["sections"].append({"node": n, "at": k, "span": n["anchor"]["span"]})
    for i, c in enumerate(chapters):
        c["end"] = chapters[i + 1]["start"] if i + 1 < len(chapters) else len(stream)

    if chapter_ids:
        chapters = [c for c in chapters if c["node"]["id"] in chapter_ids]

    manifest_chapters = []
    work.chapters.mkdir(parents=True, exist_ok=True)
    for c in chapters:
        n = c["node"]
        sec_at = {s["at"]: s for s in c["sections"]}
        skip: set[int] = set(range(c["start"], c["start"] + c["head_span"]))
        for s in c["sections"]:
            skip |= set(range(s["at"], s["at"] + s["span"]))
        items: list[dict] = []
        for k in range(c["start"], c["end"]):
            if k in skip and k not in sec_at:
                continue
            s = stream[k]
            if k in sec_at:
                sn = sec_at[k]["node"]
                items.append({"page": s["page"], "kind": "h2", "text": sn["title"], "bt": [], "it": [],
                              "sec": sn["id"], "eq": False})
                if sec_at[k]["span"] == 0 and k not in skip:
                    pass  # unanchored section: marker inserted, paragraph text kept below
                else:
                    continue
            txt = s["text"]
            kind = "p"
            if CAPTION_RE.match(txt):
                kind = "cap"
            elif (s["nl"] <= 2 and len(txt.split()) <= 12 and not txt.rstrip().endswith((".", ",", ";", ":"))
                  and (s["bold"] or (body and s["size"] >= body * 1.1))):
                kind = "h3"
            if s.get("mono") and kind == "p":
                items.append({"page": s["page"], "kind": "code", "raw": [list(x) for x in s["raw"]], "text": "", "bt": [], "it": [], "eq": False})
                continue
            is_eq, tex, num = eq_info(s) if kind == "p" else (False, "", None)
            cap_bbox = [s["x0"], s["y0"], s["x1"], s["y1"]] if kind == "cap" else None
            item = {"page": s["page"], "kind": kind, "text": txt, "bt": s["bt"], "it": s["it"], "eq": is_eq}
            if is_eq:
                item.update(tex=tex, num=num, bbox=[s["x0"], s["y0"], s["x1"], s["y1"]])
            if cap_bbox:
                item["bbox"] = cap_bbox
            items.append(item)
        items = _merge_code(_merge_equations(_merge_across_pages(items)))
        items = [p for p in items if p["text"].strip()]
        if not items:
            continue
        n_eq = n_fig = n_code = 0
        for i, p in enumerate(items):
            p["i"] = i
            if p.get("eq"):
                n_eq += 1
                p["id"] = f"{n['id']}-e{n_eq:02d}"
            elif p["kind"] == "code":
                n_code += 1
                p["id"] = f"{n['id']}-c{n_code:02d}"
            elif p["kind"] == "cap" and FIG_RE.match(p["text"]):
                n_fig += 1
                p["id"] = f"{n['id']}-f{n_fig:02d}"
        a_pg = min(p["page"] for p in items)
        b_pg = max(p.get("page_end", p["page"]) for p in items)
        words = sum(len(p["text"].split()) for p in items if p["kind"] in ("p", "cap") and not p.get("eq"))
        cid = n["id"]
        title = n["title"] + (" (continued)" if n.get("partial") else "")
        fname = f"{cid}-{slugify(n['title'])}.md"
        # markdown rendering with page markers
        md = [f"# {title}", f"<!-- chapter {cid} · pages {a_pg}–{b_pg} -->", ""]
        last_page = None
        for p in items:
            if p["page"] != last_page:
                md.append(f"<!-- p.{p['page']} -->")
                last_page = p["page"]
            if p.get("eq"):
                md.append(fmt_eq(p) + "\n")
                continue
            if p["kind"] == "code":
                md.append(f"[CODE {p['id']} · p.{p['page']}]\n```\n{p['text']}\n```\n")
                continue
            if p.get("id") and p["kind"] == "cap":
                md.append(f"[FIG {p['id']} · p.{p['page']}] {p['text']}\n")
                continue
            prefix = {"h2": "## ", "h3": "### "}.get(p["kind"], "")
            md.append(f"{prefix}{p['text']}\n")
        (work.chapters / fname).write_text("\n".join(md), encoding="utf-8")
        write_json(work.chapters / f"{cid}.paras.json",
                   {"id": cid, "title": title, "page_start": a_pg, "page_end": b_pg, "paras": items})
        secs = []
        h2s = [p for p in items if p["kind"] == "h2"]
        for j, h in enumerate(h2s):
            end_pg = h2s[j + 1]["page"] if j + 1 < len(h2s) else b_pg
            wsec = 0
            started = False
            for p in items:
                if p is h:
                    started = True
                    continue
                if started and p["kind"] == "h2":
                    break
                if started and p["kind"] in ("p", "cap"):
                    wsec += len(p["text"].split())
            secs.append({"id": h["sec"], "title": h["text"], "page_start": h["page"], "page_end": end_pg,
                         "words": wsec})
        manifest_chapters.append({
            "id": cid, "title": title, "kind": n["kind"], "part": n.get("part"),
            "partial": bool(n.get("partial")), "file": f"chapters/{fname}",
            "paras_file": f"chapters/{cid}.paras.json",
            "digest": f"digests/{cid}.md" if n["kind"] == "chapter" else None,
            "page_start": a_pg, "page_end": b_pg, "words": words,
            "est_tokens": est_tokens(" ".join(p["text"] for p in items)),
            "figures": n_fig, "code_blocks": n_code, "equations": n_eq, "equations_numbered": sum(1 for p in items if p.get("num")),
            "sections": secs,
        })

    sample = " ".join(p["text"] for p in stream[:400])
    meta_title = _pdf_title(pdf)
    ocr_n = len(extraction.get("ocr_pages", []))
    manifest = {
        "book": {"title": meta_title, "pdf": str(pdf), "total_pdf_pages": extraction["total_pdf_pages"],
                 "lang": detect_lang(sample), "sha1_head": _sha1_head(pdf),
                 "citation_note": "p.N = 1-based PDF page index (not the printed page label)"},
        "scope": {"pages": list(pages), "chapters": sorted(chapter_ids) if chapter_ids else None},
        "structure": {"source": structure["source"], "confidence": structure["confidence"]},
        "extraction": {"ocr_pages": extraction.get("ocr_pages", []), "empty_pages": extraction.get("empty_pages", []),
                       "ocr_lang": extraction.get("ocr_lang"),
                       "ocr_available": extraction.get("ocr_available"),
                       "quality": "ocr" if ocr_n > 0.5 * (pages[1] - pages[0] + 1) else "text"},
        "chapters": manifest_chapters,
        "totals": {"words": sum(c["words"] for c in manifest_chapters),
                   "est_tokens": sum(c["est_tokens"] for c in manifest_chapters)},
    }
    write_json(work.manifest, manifest)
    return manifest


def _pdf_title(pdf: Path) -> str:
    try:
        from .extract import _open
        d = _open(pdf)
        t = (d.metadata or {}).get("title", "").strip()
        d.close()
        if t and len(t) > 2:
            return t
    except Exception:
        pass
    return pdf.stem.replace("_", " ")


def _sha1_head(pdf: Path) -> str:
    with open(pdf, "rb") as f:
        return hashlib.sha1(f.read(1 << 20)).hexdigest()[:12]
