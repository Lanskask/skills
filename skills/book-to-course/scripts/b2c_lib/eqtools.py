"""On-demand equation helpers: look up a drafted equation, crop its picture from the PDF, render a page.

Images are made only when asked for (`b2c.py eq --image`, `b2c.py page-image`) so `prepare` stays cheap.
Open the PNG with the Read tool (the model sees it) when the LaTeX draft looks wrong: this is the
fallback for formulas the text layer cannot express (fractions, matrices, scanned books)."""
from __future__ import annotations

from pathlib import Path

from .common import Work, read_json
from .extract import _open


def _chapter_of(eq_id: str) -> str:
    return eq_id.split("-e")[0]


def find_eq(work: Work, eq_id: str) -> dict:
    manifest = read_json(work.manifest)
    ch = next((c for c in manifest["chapters"] if c["id"] == _chapter_of(eq_id)), None)
    if ch is None:
        raise KeyError(f"unknown chapter in equation id {eq_id!r}")
    for p in read_json(work.root / ch["paras_file"])["paras"]:
        if p.get("id") == eq_id:
            return p
    raise KeyError(f"no equation {eq_id!r} (see `b2c.py eq --chapter {ch['id']} --list`)")


def list_eqs(work: Work, chapter: str, limit: int = 60) -> list[dict]:
    manifest = read_json(work.manifest)
    ch = next(c for c in manifest["chapters"] if c["id"] == chapter)
    return [p for p in read_json(work.root / ch["paras_file"])["paras"] if p.get("eq")][:limit]


def crop_eq(work: Work, pdf: Path, eq: dict, dpi: int = 200, pad: float = 6.0) -> Path | None:
    x0, y0, x1, y1 = eq["bbox"]
    if not (x1 > x0 and y1 > y0):
        return None  # OCR page without geometry: use page-image
    import pymupdf

    out = work.root / "eq" / f"{eq['id']}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = _open(pdf)
    try:
        page = doc[eq["page"] - 1]
        clip = pymupdf.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
        page.get_pixmap(dpi=dpi, clip=clip).save(str(out))
    finally:
        doc.close()
    return out


def page_image(work: Work, pdf: Path, page_no: int, dpi: int = 110) -> Path:
    out = work.root / "eq" / f"page-{page_no:04d}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = _open(pdf)
    try:
        doc[page_no - 1].get_pixmap(dpi=dpi).save(str(out))
    finally:
        doc.close()
    return out
