"""Stage 2 — strip running headers/footers, page numbers and repeated boilerplate.

Reads work/pages/*.json, writes work/pages_clean/*.json and work/clean_report.json.
Method (all deterministic):
  * a line is a *band candidate* if it sits in the top/bottom 9% of the page (or is one of the
    first/last two lines on OCR pages, which have no coordinates);
  * its key is the lower-cased text with digits replaced by '#', so "12  Foo" and "13  Foo" collide;
  * band candidates whose key occurs on >= 3 pages (>= 2 for tiny ranges) are removed;
  * any line (>= 12 chars) whose key occurs on >= max(5, 30%) of pages is removed as boilerplate;
  * bare page numbers ("12", "- 12 -", "Page 12 of 300", "Стр. 12", roman numerals in a band) are removed.
Every removed pattern is listed in clean_report.json so the step is auditable.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

from .common import Work, read_json, write_json

BAND = 0.09
_PAGENUM = re.compile(
    r"^\s*[-–—•]?\s*(\d{1,4})\s*[-–—•]?\s*$"
    r"|^\s*(page|стр\.?|страница|с\.)\s*\d+(\s*(of|из|/)\s*\d+)?\s*$",
    re.I,
)
_ROMAN = re.compile(r"^\s*[ivxlcdm]{1,7}\s*$", re.I)


def key_of(text: str) -> str:
    k = re.sub(r"\d+", "#", text.lower())
    return re.sub(r"[\W_]+", " ", k, flags=re.UNICODE).strip()


def _band_flags(page: dict) -> list[int]:
    """2 = inside the top/bottom 9% band; 1 = one of the first/last two lines of the page (headers outside the band: big margins,
    tight page boxes); 0 = body."""
    lines = page["lines"]
    h = page.get("height") or 0
    flags = []
    geom = [i for i, ln in enumerate(lines) if ln["y1"] > 0]
    order = sorted(geom, key=lambda i: lines[i]["y0"])
    edge = set(order[:2]) | set(order[-2:])
    for idx, ln in enumerate(lines):
        if ln["y1"] > 0 and h:
            flags.append(2 if (ln["y1"] < h * BAND or ln["y0"] > h * (1 - BAND)) else 1 if idx in edge else 0)
        else:  # OCR page: no geometry
            flags.append(2 if (idx < 2 or idx >= len(lines) - 2) else 0)
    return flags


_NUMTOK = re.compile(r"^\s*(\d{1,4})(?:\s|$)|(?:\s)(\d{1,4})\s*$")


def _number_in(text: str) -> int | None:
    m = _NUMTOK.search(text)
    return int(m.group(1) or m.group(2)) if m else None


def _page_number_keys(raw: list[dict], flags_by_page: dict[int, list[int]]) -> set[str]:
    """Keys of margin lines that carry the PAGE NUMBER: their number follows the PDF page index (124, 125, 126 ...),
    unlike 'Chapter 1' / 'Chapter 2' labels. Returns digit-masked keys."""
    from collections import Counter

    pairs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for pg in raw:
        for ln, fl in zip(pg["lines"], flags_by_page[pg["page"]]):
            if fl >= 1:
                n = _number_in(ln["t"])
                if n is not None:
                    pairs[key_of(ln["t"])].append((pg["page"], n))
    keys = set()
    for k, ps in pairs.items():
        offs = Counter(p - n for p, n in ps)
        support = offs.most_common(1)[0][1]
        if support >= (3 if k == "#" else 2):
            keys.add(k)
    return keys


def clean(work: Work, pages: tuple[int, int]) -> dict:
    out_dir = work.root / "pages_clean"
    out_dir.mkdir(parents=True, exist_ok=True)
    a, b = pages
    raw = [read_json(work.pages / f"{p:04d}.json") for p in range(a, b + 1)
           if (work.pages / f"{p:04d}.json").exists()]
    n = len(raw)
    band_thr = 2 if n < 6 else 3
    boiler_thr = max(5, math.ceil(0.30 * n))

    band_count: dict[str, set[int]] = defaultdict(set)   # lines inside the 9% margin band
    edge_count: dict[str, set[int]] = defaultdict(set)   # first/last two lines of a page (superset of the band lines)
    any_count: dict[str, set[int]] = defaultdict(set)
    example: dict[str, str] = {}
    flags_by_page = {}
    for pg in raw:
        flags = _band_flags(pg)
        flags_by_page[pg["page"]] = flags
        blk_len: dict[int, int] = defaultdict(int)
        for ln in pg["lines"]:
            blk_len[ln["blk"]] += 1
        for ln, fl in zip(pg["lines"], flags):
            k = key_of(ln["t"])
            if not k:
                continue
            example.setdefault(k, ln["t"])
            if blk_len[ln["blk"]] == 1:  # boilerplate = a line standing alone, never a wrapped body line
                any_count[k].add(pg["page"])
            if fl == 2:
                band_count[k].add(pg["page"])
            if fl >= 1:
                edge_count[k].add(pg["page"])

    pn_keys = _page_number_keys(raw, flags_by_page)   # margin lines whose number follows the page index
    band_keys = {k for k, pgs in band_count.items() if len(pgs) >= band_thr and k != "#"}
    # headers outside the 9% band: accepted when they carry the page number (2 pages enough) or repeat on >= 40% of pages;
    # NOT when they merely repeat with a changing digit ("Chapter 1", "Chapter 2": numbers do not follow the page index)
    edge_keys = {k for k, pgs in edge_count.items()
                 if k not in band_keys and k != "#" and ((k in pn_keys and len(pgs) >= 2) or len(pgs) >= max(band_thr, math.ceil(0.4 * n)))}
    boiler_keys = {k for k, pgs in any_count.items() if len(k) >= 12 and len(pgs) >= boiler_thr and k not in band_keys | edge_keys}
    drop_keys = {**{k: "running header/footer" for k in band_keys}, **{k: "running header (outside margin band)" for k in edge_keys},
                 **{k: "repeated boilerplate" for k in boiler_keys}}

    removed_total = 0
    pagenum_removed = 0
    for pg in raw:
        keep, removed = [], []
        flags = flags_by_page[pg["page"]]
        for ln, fl in zip(pg["lines"], flags):
            k = key_of(ln["t"])
            is_num = bool(_PAGENUM.match(ln["t"])) or (fl == 2 and bool(_ROMAN.match(ln["t"])))
            lone_num = is_num and (fl == 2 or (fl == 1 and "#" in pn_keys))
            if lone_num or (k in band_keys and fl == 2) or (k in edge_keys and fl >= 1) or k in boiler_keys:
                removed.append(ln["t"])
                pagenum_removed += lone_num
            else:
                keep.append(ln)
        removed_total += len(removed)
        pg2 = dict(pg, lines=keep, removed=removed)
        write_json(out_dir / f"{pg['page']:04d}.json", pg2)

    report = {
        "pages": n,
        "lines_removed": removed_total,
        "page_numbers_removed": int(pagenum_removed),
        "patterns": [
            {"key": k, "kind": kind, "pages": len(edge_count.get(k) or any_count[k]), "example": example[k]}
            for k, kind in sorted(drop_keys.items())
        ],
    }
    write_json(work.root / "clean_report.json", report)
    return report
