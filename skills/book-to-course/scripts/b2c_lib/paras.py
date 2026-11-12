"""Paragraph reconstruction from cleaned lines. Shared by split, validate and select so that
quote checking sees exactly the same text the LLM was shown."""
from __future__ import annotations

import re
from collections import Counter

from .common import Work, read_json

_END = re.compile(r"[.!?…:;»\")\]]$")


def body_size(pages: list[dict]) -> float:
    """Most common font size weighted by characters = body text size (0 if OCR-only)."""
    c: Counter = Counter()
    for pg in pages:
        for ln in pg["lines"]:
            if ln["s"] > 0:
                c[ln["s"]] += ln.get("w", len(ln["t"]))
    return c.most_common(1)[0][0] if c else 0.0


def join_lines(prev: str, nxt: str) -> str:
    if len(prev) > 1 and prev.endswith("-") and prev[-2].isalpha() and nxt[:1].islower():
        return prev[:-1] + nxt  # de-hyphenate across the line break
    return prev + " " + nxt


def build_paras(lines: list[dict]) -> list[dict]:
    """Group lines into paragraphs: same block, and no unusually large vertical gap."""
    paras: list[dict] = []
    cur: dict | None = None
    prev: dict | None = None
    for ln in lines:
        new = cur is None or ln["blk"] != prev["blk"] or bool(ln.get("mono")) != bool(prev.get("mono"))
        if not new and ln["y0"] and prev["y1"]:
            gap = ln["y0"] - prev["y1"]
            if gap > 0.55 * max(ln["s"], 1) and _END.search(prev["t"]):
                new = True
        if new:
            cur = {"text": ln["t"], "size": ln["s"], "bold": ln["b"], "bt": list(ln["bt"]),
                   "it": list(ln["it"]), "nl": 1, "y0": ln["y0"], "y1": ln["y1"],
                   "x0": ln.get("x0", 0), "x1": ln.get("x1", 0),
                   "m": bool(ln.get("m")), "ml": 1 if ln.get("m") else 0,
                   "tx": [ln["tx"]] if ln.get("m") else [],
                   "mono": bool(ln.get("mono")), "raw": [(ln["t"], ln.get("x0", 0), ln.get("x1", 0))]}
            paras.append(cur)
        else:
            cur["text"] = join_lines(cur["text"], ln["t"])
            cur["bold"] = cur["bold"] and ln["b"]
            cur["bt"] += ln["bt"]
            cur["it"] += ln["it"]
            cur["nl"] += 1
            cur["mono"] = cur["mono"] and bool(ln.get("mono"))
            cur["raw"].append((ln["t"], ln.get("x0", 0), ln.get("x1", 0)))
            cur["y1"] = ln["y1"]
            cur["x0"], cur["x1"] = min(cur["x0"], ln.get("x0", 0)), max(cur["x1"], ln.get("x1", 0))
            if ln.get("m"):
                cur["m"] = True
                cur["ml"] += 1
                cur["tx"].append(ln["tx"])
        prev = ln
    return paras


def load_clean_pages(work: Work, a: int, b: int) -> list[dict]:
    d = work.root / "pages_clean"
    return [read_json(d / f"{p:04d}.json") for p in range(a, b + 1) if (d / f"{p:04d}.json").exists()]


def page_text(work: Work, page: int) -> str:
    """Cleaned, de-hyphenated text of one page (used by quote validation)."""
    f = work.root / "pages_clean" / f"{page:04d}.json"
    if not f.exists():
        return ""
    return "\n".join(p["text"] for p in build_paras(read_json(f)["lines"]))


def fmt_eq(p: dict) -> str:
    """One-line pack/markdown form of an equation item. LaTeX is a machine draft, never ground truth."""
    num = f" · eq.({p['num']})" if p.get("num") else ""
    tex = p.get("tex") or p["text"]
    return f"[EQ {p['id']} · p.{p['page']}{num}] draft: ${tex}$"


def code_text(raw: list[tuple[str, float, float]]) -> str:
    """Rebuild a code listing from monospace lines: one line per line, indentation from x offsets (char width from the lines)."""
    widths = [(x1 - x0) / max(len(t), 1) for t, x0, x1 in raw if x1 > x0 and len(t.strip()) > 3]
    cw = sorted(widths)[len(widths) // 2] if widths else 0
    base = min((x0 for t, x0, x1 in raw if x1 > x0 and t.strip()), default=0)
    out = []
    for t, x0, x1 in raw:
        t = t.rstrip()
        lead = len(t) - len(t.lstrip())
        ind = round((x0 - base) / cw) if cw and x1 > x0 else lead
        out.append(" " * max(ind, 0) + t.lstrip() if t.strip() else "")
    return "\n".join(out).strip("\n")


def fmt_code(p: dict, max_lines: int = 30) -> str:
    lines = p["text"].split("\n")
    body = "\n".join(lines[:max_lines]) + (f"\n# … {len(lines) - max_lines} more line(s) …" if len(lines) > max_lines else "")
    return f"[CODE {p['id']} · p.{p['page']}]\n```\n{body}\n```"


def page_code(work: Work, page: int) -> str:
    """Code listings (monospace paragraphs) of one cleaned page, with line breaks."""
    f = work.root / "pages_clean" / f"{page:04d}.json"
    if not f.exists():
        return ""
    return "\n".join(code_text(p["raw"]) for p in build_paras(read_json(f)["lines"]) if p.get("mono"))
