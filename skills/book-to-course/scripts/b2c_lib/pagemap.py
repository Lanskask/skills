"""Map printed page numbers (as in a book's table of contents) to PDF page indexes.

The skill cites 1-based PDF page indexes everywhere; a user quoting "Chapter 6, page 123" means the printed number.
Method: read the margin bands (top/bottom 9%) of every page, collect (printed, pdf) pairs from lines that are a bare number,
start with a number ("124 Random Numbers") or end with one ("Random Numbers 124"), then take the most common offset among the
pairs near the requested range. Needs >= 3 agreeing pages; otherwise it refuses and you pass --pages.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .extract import _open

_NUM = re.compile(r"^\s*(\d{1,4})\s*$")
_LEAD = re.compile(r"^\s*(\d{1,4})\s{1,6}\S")
_TRAIL = re.compile(r"\S\s{1,6}(\d{1,4})\s*$")
BAND = 0.09


def printed_numbers(pdf: Path) -> list[tuple[int, int]]:
    """[(pdf_page, printed_number)] for every page where a margin line looks like a page number."""
    doc = _open(pdf)
    pairs = []
    try:
        for i in range(doc.page_count):
            page = doc[i]
            h = page.rect.height
            found = set()
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    y0, y1 = line["bbox"][1], line["bbox"][3]
                    if not (y1 < h * BAND or y0 > h * (1 - BAND)):
                        continue
                    t = "".join(s["text"] for s in line["spans"]).replace(" ", " ").strip()
                    for rx in (_NUM, _LEAD, _TRAIL):
                        m = rx.match(t) if rx is not _TRAIL else rx.search(t)
                        if m:
                            found.add(int(m.group(1)))
                            break
            for n in found:
                pairs.append((i + 1, n))
    finally:
        doc.close()
    return pairs


def find_headings(pdf: Path, queries: list[str], max_hits: int = 6) -> dict[str, list[dict]]:
    """Where does a heading appear? For each query: pages with a short line containing it, flagged heading-like (bigger/bold than body)
    and skipping contents-page entries (dot leaders). For books without bookmarks."""
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s).lower()
        return re.sub(r"[^\w ]+", "", re.sub(r"\s+", " ", s)).strip()

    nq = {q: norm(q) for q in queries}
    hits: dict[str, list[dict]] = {q: [] for q in queries}
    doc = _open(pdf)
    try:
        for i in range(doc.page_count):
            d = doc[i].get_text("dict")
            sizes = [s["size"] for b in d["blocks"] if b.get("type") == 0 for l in b["lines"] for s in l["spans"] for _ in s["text"]]
            body = sorted(sizes)[len(sizes) // 2] if sizes else 0
            for b in d["blocks"]:
                if b.get("type") != 0:
                    continue
                for line in b["lines"]:
                    sp = [s for s in line["spans"] if s["text"].strip()]
                    t = " ".join(s["text"].strip() for s in sp)
                    if not t or len(t) > 110 or re.search(r"\.\s?\.\s?\.|…", t):
                        continue
                    n = norm(t)
                    for q, nqq in nq.items():
                        if nqq and nqq in n and len(n) <= len(nqq) + 14:
                            size = max(s["size"] for s in sp)
                            bold = all(bool(s["flags"] & 16) or "bold" in s["font"].lower() for s in sp)
                            hits[q].append({"pdf_page": i + 1, "text": t, "size": round(size, 1), "body": round(body, 1),
                                            "heading_like": bool(body and (size >= body * 1.12 or bold))})
    finally:
        doc.close()
    return {q: sorted(h, key=lambda x: (not x["heading_like"], x["pdf_page"]))[:max_hits] for q, h in hits.items()}


def printed_to_pdf(pdf: Path, a: int, b: int, window: int = 40, anchor: str | None = None) -> dict:
    """-> {"pdf_pages": (A, B), "offset": k, "support": n, "of": m}. Raises ValueError if the offset is not reliable."""
    if anchor:  # fallback: the heading that opens the range tells where printed page `a` is
        h = [x for x in find_headings(pdf, [anchor])[anchor] if x["heading_like"]]
        if not h:
            raise ValueError(f"heading {anchor!r} not found as a heading; check `b2c.py find`")
        off = h[0]["pdf_page"] - a
        return {"pdf_pages": (a + off, b + off), "offset": off, "support": 1, "of": 1, "via": f"heading {anchor!r} on PDF p.{h[0]['pdf_page']}"}
    pairs = printed_numbers(pdf)
    near = [(p, n) for p, n in pairs if a - window <= n <= b + window]
    if not near:
        raise ValueError("no printed page numbers found near that range; try --anchor 'Heading text' (see `b2c.py find`), or use --pages")
    c = Counter(p - n for p, n in near)
    offset, support = c.most_common(1)[0]
    if support < 3 or support < 0.5 * len({p for p, _ in near}):
        raise ValueError(f"printed page numbers are not consistent here (best offset {offset} seen on {support} pages); "
                         "try --anchor 'Heading text' (see `b2c.py find`), or use --pages with PDF page numbers")
    return {"pdf_pages": (a + offset, b + offset), "offset": offset, "support": support, "of": len({p for p, _ in near})}
