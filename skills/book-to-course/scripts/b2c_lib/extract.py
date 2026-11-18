"""Stage 1 — per-page text extraction with font info; OCR fallback for scanned pages.

Output: work/pages/NNNN.json  {page, label, ocr, height, lines:[{t,s,b,i,blk,y0,y1,bt,it}]}
`page` is the 1-based PDF page index. It is the canonical page number used in every citation.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from .common import Work, write_json
from .mathtex import MATH_CHARS, MATH_FONT, MONO_FONT, fix_glyphs, spans_to_tex, text_to_tex

MIN_CHARS_TEXT_PAGE = 40  # fewer extractable chars than this + an image => treat as scanned


def _open(pdf: Path):
    import pymupdf  # imported lazily so `--help` works without the dependency

    return pymupdf.open(str(pdf))


def pdf_outline(pdf: Path) -> list[list]:
    doc = _open(pdf)
    try:
        return [[lvl, title.strip(), page] for lvl, title, page in doc.get_toc(simple=True) if page > 0]
    finally:
        doc.close()


def page_count(pdf: Path) -> int:
    doc = _open(pdf)
    try:
        return doc.page_count
    finally:
        doc.close()


_LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}
_LIG_RE = re.compile("[\ufb00-\ufb06]")
_ACCENT = {"\u00a8": "\u0308", "\u00b4": "\u0301", "\u02c6": "\u0302", "\u02dc": "\u0303"}
_ACCENT_RE = re.compile("([\u00a8\u00b4\u02c6\u02dc])([aeiouyAEIOUY])")  # no backtick: code listings use it


def _normalise(text: str) -> str:
    """NBSP/thin spaces -> space; MuPDF reports every hyphen as a soft hyphen U+00AD -> '-'; ligatures (ﬀ ﬁ ﬂ) are
    expanded; a spacing accent glued before a vowel (TeX-era PDFs give 'Schr¨odinger') is composed ('Schrödinger')."""
    text = re.sub(r"[\u00a0\u2002-\u200a\u202f]", " ", text).replace("\u00ad", "-")
    text = _LIG_RE.sub(lambda m: _LIGATURES[m.group(0)], text)
    text = fix_glyphs(text)
    if "\u00a8" in text or "\u00b4" in text or "\u02c6" in text or "\u02dc" in text:
        text = unicodedata.normalize("NFC", _ACCENT_RE.sub(lambda m: m.group(2) + _ACCENT[m.group(1)], text))
    return text.strip()


def _flags_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or bool(re.search(r"bold|black|heavy|semibold", span["font"], re.I))


def _flags_italic(span: dict) -> bool:
    return bool(span["flags"] & 2) or bool(re.search(r"italic|oblique", span["font"], re.I))


def _hidden_text_layer(page) -> bool:
    """Most characters drawn invisible (PDF render mode 3): a scan's OCR layer, whose font (often Courier) means nothing."""
    kinds = [t["type"] for t in page.get_texttrace() for _ in t["chars"]]
    return bool(kinds) and kinds.count(3) > 0.8 * len(kinds)


def _lines_from_dict(pdict: dict, ocr_layer: bool = False) -> list[dict]:
    lines: list[dict] = []
    blk = 0
    for block in pdict["blocks"]:
        if block.get("type") != 0:
            continue
        added = False
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = _normalise("".join(s["text"] for s in line["spans"]))
            if not text:
                continue
            weight = sum(len(s["text"].strip()) for s in spans)
            size = max(spans, key=lambda s: len(s["text"].strip()))["size"]
            all_bold = all(_flags_bold(s) for s in spans)
            all_ital = all(_flags_italic(s) for s in spans)
            bt = [] if all_bold else [s["text"].strip() for s in spans if _flags_bold(s)]
            it = [] if all_ital else [s["text"].strip() for s in spans if _flags_italic(s)]
            mchars = sum(1 for c in text if c in MATH_CHARS)
            mfont = any(MATH_FONT.search(s["font"]) for s in spans)
            mono = not ocr_layer and all(bool(s["flags"] & 8) or bool(MONO_FONT.search(s["font"])) for s in spans)
            rec = {
                "t": text,
                "s": round(size, 1),
                "b": all_bold,
                "i": all_ital,
                "blk": blk,
                "x0": round(line["bbox"][0], 1),
                "x1": round(line["bbox"][2], 1),
                "y0": round(line["bbox"][1], 1),
                "y1": round(line["bbox"][3], 1),
                "bt": [_normalise(x) for x in bt if 3 <= len(x) <= 40],
                "it": [_normalise(x) for x in it if 3 <= len(x) <= 40],
                "w": weight,
            }
            if mono:  # monospace line = program code, never an equation (keep raw text with indentation geometry)
                rec["mono"] = True
                rec["t"] = "".join(s["text"] for s in line["spans"]).replace("\u00a0", " ").rstrip()
            elif mfont or mchars >= 2:  # math-looking line: keep a LaTeX draft built from span geometry
                rec["m"] = True
                rec["tx"] = spans_to_tex(line["spans"])
            lines.append(rec)
            added = True
        if added:
            blk += 1
    return lines


def tesseract_langs() -> set[str]:
    if not shutil.which("tesseract"):
        return set()
    r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return {x.strip() for x in r.stdout.splitlines()[1:] if x.strip()}


def ocr_page(page, lang: str, dpi: int = 250) -> list[dict]:
    """OCR one page with tesseract. Returns lines without font info (s=0)."""
    pix = page.get_pixmap(dpi=dpi)
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        pix.save(str(png))
        r = subprocess.run(
            ["tesseract", str(png), "stdout", "-l", lang, "--psm", "3"],
            capture_output=True, text=True,
        )
    lines: list[dict] = []
    blk = 0
    for para in re.split(r"\n\s*\n", r.stdout):
        got = False
        for ln in para.splitlines():
            ln = ln.strip()
            if ln:
                rec = {"t": ln, "s": 0, "b": False, "i": False, "blk": blk, "x0": 0, "x1": 0,
                       "y0": 0, "y1": 0, "bt": [], "it": [], "w": len(ln)}
                if sum(1 for c in ln if c in MATH_CHARS) >= 2:
                    rec["m"], rec["tx"] = True, text_to_tex(ln)
                lines.append(rec)
                got = True
        if got:
            blk += 1
    return lines


def extract(pdf: Path, work: Work, pages: tuple[int, int] | None, ocr: str = "auto",
            ocr_lang: str | None = None) -> dict:
    """Extract pages [a..b] (1-based, inclusive). Returns a small summary dict."""
    work.mkdirs()
    doc = _open(pdf)
    n = doc.page_count
    a, b = pages or (1, n)
    a, b = max(1, a), min(n, b)
    langs = tesseract_langs()
    if ocr_lang is None:
        ocr_lang = "+".join(x for x in ("eng", "rus") if x in langs) or "eng"
    ocr_pages: list[int] = []
    empty_pages: list[int] = []
    for pno in range(a, b + 1):
        page = doc[pno - 1]
        lines = _lines_from_dict(page.get_text("dict"), _hidden_text_layer(page))
        chars = sum(len(x["t"]) for x in lines)
        used_ocr = False
        scanned = chars < MIN_CHARS_TEXT_PAGE and bool(page.get_images(full=False))
        if ocr == "force" or (ocr == "auto" and scanned):
            if langs:
                lines, used_ocr = ocr_page(page, ocr_lang), True
                ocr_pages.append(pno)
        if not lines:
            empty_pages.append(pno)
        write_json(
            work.pages / f"{pno:04d}.json",
            {"page": pno, "label": page.get_label() or "", "ocr": used_ocr,
             "height": round(page.rect.height, 1), "lines": lines},
        )
    doc.close()
    return {"pages": [a, b], "total_pdf_pages": n, "ocr_pages": ocr_pages,
            "empty_pages": empty_pages, "ocr_lang": ocr_lang if ocr_pages else None,
            "ocr_available": bool(langs)}
