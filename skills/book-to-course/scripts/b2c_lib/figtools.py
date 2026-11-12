"""Book figures: find the picture belonging to a caption and crop it from the PDF (on demand).

Method (no ML): collect the page's vector-drawing clusters and embedded images, take the group of graphics directly above the
caption (or below it, for captions printed over the figure), add the text lines that sit inside that group (axis labels), crop.
Works for LaTeX/Word PDFs with real graphics; fails (returns None) on figures that are only scanned pixels of a full page:
use `page-image` then. The crop is for personal study material; do not republish a book's figures.
"""
from __future__ import annotations

from pathlib import Path

from .common import Work, read_json
from .extract import _open


def find_fig(work: Work, fig_id: str) -> dict:
    manifest = read_json(work.manifest)
    cid = fig_id.split("-f")[0]
    ch = next((c for c in manifest["chapters"] if c["id"] == cid), None)
    if ch is None:
        raise KeyError(f"unknown chapter in figure id {fig_id!r}")
    for p in read_json(work.root / ch["paras_file"])["paras"]:
        if p.get("id") == fig_id:
            return p
    raise KeyError(f"no figure {fig_id!r} (see `b2c.py fig --chapter {cid} --list`)")


def list_figs(work: Work, chapter: str) -> list[dict]:
    manifest = read_json(work.manifest)
    ch = next(c for c in manifest["chapters"] if c["id"] == chapter)
    return [p for p in read_json(work.root / ch["paras_file"])["paras"] if p["kind"] == "cap" and p.get("id")]


def _graphics(page) -> list:
    import pymupdf

    rects = []
    try:
        rects += [pymupdf.Rect(r) for r in page.cluster_drawings()]
    except Exception:  # noqa: BLE001  (older MuPDF)
        rects += [pymupdf.Rect(d["rect"]) for d in page.get_drawings()]
    for im in page.get_image_info():
        rects.append(pymupdf.Rect(im["bbox"]))
    h, w = page.rect.height, page.rect.width
    # drop page-wide rules/frames and specks
    return [r for r in rects if r.width > 18 and r.height > 12 and not (r.width > 0.95 * w and r.height > 0.9 * h)]


def figure_rect(page, cap_bbox: list[float], reach: float = 460.0, gap: float = 22.0):
    """Union of the graphics chain adjacent to the caption (above first, then below), plus inner text; None if none."""
    import pymupdf

    cx0, cy0, cx1, cy1 = cap_bbox
    gfx = _graphics(page)
    for direction in ("above", "below"):
        if direction == "above":
            cand = [r for r in gfx if r.y1 <= cy0 + 6 and r.y1 >= cy0 - reach]
            cand.sort(key=lambda r: -r.y1)
        else:
            cand = [r for r in gfx if r.y0 >= cy1 - 6 and r.y0 <= cy1 + reach]
            cand.sort(key=lambda r: r.y0)
        if not cand:
            continue
        union = pymupdf.Rect(cand[0])
        for r in cand[1:]:
            near = (r.y1 >= union.y0 - gap) if direction == "above" else (r.y0 <= union.y1 + gap)
            if near:
                union |= r
        if union.height < 14 or union.width < 20:
            continue
        pad = pymupdf.Rect(union.x0 - 52, union.y0 - 16, union.x1 + 52, union.y1 + 16)
        for b in page.get_text("blocks"):
            br = pymupdf.Rect(b[:4])
            if b[6] == 0 and pad.contains(br) and not br.intersects(pymupdf.Rect(cx0, cy0, cx1, cy1)):
                union |= br
        return (union + (-4, -4, 4, 4)) & page.rect
    return None


def crop_fig(pdf: Path, fig: dict, out: Path, dpi: int = 170) -> Path | None:
    x0, y0, x1, y1 = fig["bbox"]
    if not (x1 > x0 and y1 > y0):
        return None  # OCR page: no geometry
    doc = _open(pdf)
    try:
        page = doc[fig["page"] - 1]
        rect = figure_rect(page, fig["bbox"])
        if rect is None:
            return None
        out.parent.mkdir(parents=True, exist_ok=True)
        page.get_pixmap(dpi=dpi, clip=rect).save(str(out))
        return out
    finally:
        doc.close()
