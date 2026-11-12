"""Regression tests for problems seen on a real textbook: no bookmarks, split running heads, code listings, derivation fragments,
garbled math in problems, glyph variants, small-scope packs. Sample: make_sample_pdf.py --kind book2."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import ROOT, make_pdf, prepare  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from b2c_lib import mathtex, pagemap, render, select, validate  # noqa: E402
from b2c_lib.common import read_json, write_json  # noqa: E402
from b2c_lib.paras import page_text  # noqa: E402


@pytest.fixture(scope="module")
def book2(tmp_path_factory):
    return make_pdf("book2", tmp_path_factory.mktemp("b2") / "book2.pdf")


def _last(pdf) -> int:
    import pymupdf
    return pymupdf.open(str(pdf)).page_count


@pytest.fixture()
def tb(book2, tmp_path):
    work, mf = prepare(book2, tmp_path / "c", pages=(9, _last(book2)), mode="headings")
    return work, mf


# ── 1. pages without bookmarks ───────────────────────────────────────────

def test_pagemap_with_number_split_from_title(book2):
    last = _last(book2)
    m = pagemap.printed_to_pdf(book2, 123, last - 8 + 122)
    assert m["pdf_pages"] == (9, last) and m["offset"] == -114 and m["support"] >= 10


def test_find_headings_and_anchor_fallback(book2):
    hits = pagemap.find_headings(book2, ["Monte Carlo Techniques", "Stochastic Methods"])
    assert hits["Monte Carlo Techniques"][0]["pdf_page"] == 9 and hits["Monte Carlo Techniques"][0]["heading_like"]
    assert hits["Stochastic Methods"][0]["heading_like"]
    m = pagemap.printed_to_pdf(book2, 123, 130, anchor="Monte Carlo Techniques")
    assert m["pdf_pages"] == (9, 16) and "heading" in m["via"]


# ── 2. running heads ─────────────────────────────────────────────────────

def test_split_running_heads_removed_and_no_fake_sections(tb):
    work, mf = tb
    rep = read_json(work.root / "clean_report.json")
    assert rep["lines_removed"] >= 20
    ch = [c for c in mf["chapters"] if c["kind"] == "chapter"]
    assert [c["title"] for c in ch] == ["6 Monte Carlo Techniques", "7 Stochastic Methods"]
    assert [[s["title"] for s in c["sections"]] for c in ch][0] == ["6.1 Random Numbers", "6.2 Integration", "6.3 Problems"]
    md = " ".join(p.read_text() for p in work.chapters.glob("*.md"))
    assert "Monte Carlo Techniques\n" not in md.replace("# 6 Monte Carlo Techniques\n", "") and "\n124\n" not in md and "\n125\n" not in md


def test_chapter_labels_are_not_mistaken_for_headers(tmp_path):
    # 'Chapter 1' ... 'Chapter 5' repeat with a changing digit but do not follow the page index: they must stay
    work, mf = prepare(make_pdf("en", tmp_path / "en.pdf"), tmp_path / "c")
    assert [c["title"] for c in mf["chapters"] if c["kind"] == "chapter"][0] == "Chapter 1. Introduction to Plasma"


# ── 3. code is not an equation ───────────────────────────────────────────

def test_code_detected_with_indentation_and_not_as_equation(tb):
    work, mf = tb
    ch = {c["id"]: c for c in mf["chapters"]}
    assert ch["ch02"]["code_blocks"] == 1 and ch["ch02"]["equations"] == 1
    md = next(work.chapters.glob("ch02-*.md")).read_text()
    assert "[CODE ch02-c01 · p.9]\n```\nimport random\ncount = 0\nfor i in range(100):\n   count = count+1\n```" in md
    assert "EQ ch02-e01" in md and "import random" not in md.split("EQ ch02-e01")[1]


def test_derivation_lines_are_one_equation(tb):
    work, _ = tb
    paras = read_json(work.root / "chapters" / "ch02.paras.json")["paras"]
    eqs = [p for p in paras if p.get("eq")]
    assert len(eqs) == 1 and eqs[0]["num"] == "6.2" and eqs[0]["text"].count("=") >= 3


def test_math_font_regex_only_matches_math_fonts():
    for f in ("CMR10", "CMBX12", "CMTI10", "CMSS10", "LMRoman10-Regular", "STIXGeneral", "Courier"):
        assert not mathtex.MATH_FONT.search(f), f
    for f in ("CMMI10", "CMSY10", "CMEX10", "MSBM10", "Symbol", "CambriaMath"):
        assert mathtex.MATH_FONT.search(f), f
    assert mathtex.MONO_FONT.search("CMTT10") and mathtex.MONO_FONT.search("Menlo-Regular") and not mathtex.MONO_FONT.search("MonotypeCorsiva")


# ── 4/5. symbols that text layers lose, glyph variants ───────────────────

def test_grounding_ignores_sum_integral_and_unifies_glyphs():
    s, miss = mathtex.grounding(r"\sum_i \hbar \Delta x", "X ¯h ∆x")        # sum -> 'X', hbar -> '¯h', increment sign
    assert s == 1.0 and not miss
    assert mathtex.grounding(r"\int f(x)\,dx", "(integral sign dropped by extractor)")[0] is None  # nothing to verify, no false error
    assert mathtex.fix_glyphs("¯h ∆ ħ") == "ℏ Δ ℏ"


# ── scoped helpers for lesson drafts ─────────────────────────────────────

QUOTE = "A charged particle in a uniform magnetic field moves along a helix around a field line."


def _lesson(page_quote=9, extra=None):
    return {
        "id": "L-01", "title": "Random numbers in practice", "metaphor": "Think of rolling dice many times to learn the average.",
        "hook": "A computer can only pretend to roll dice, yet the pretence works well.",
        "why_care": "Every Monte Carlo estimate is only as good as its random numbers.",
        "screens": [
            {"id": "s1", "heading": "The idea", "covers": [0],
             "blocks": [{"type": "quote", "text": QUOTE, "page": page_quote, "meaning": "Charges spiral around magnetic field lines, a [[helix]]."},
                        {"type": "text", "text": "A [[helix]] is a spiral path that also moves forward along an axis, like the thread of a screw or a spring seen from the side. "
                                                  "Picture a coil of wire: every turn is a circle, yet the whole coil advances in one direction. The same shape appears whenever a "
                                                  "motion in a circle is combined with a steady drift along a line, which is why it shows up so often in physics.", "cite": [9]}]},
            {"id": "s2", "heading": "Try it", "covers": [1], "blocks": (extra or []) + [
                {"type": "callout", "variant": "info", "title": "Note", "text": "Run it a few times and compare the results.", "cite": [9]}]},
        ],
        "quiz": [{"question": "You double the number of samples in a Monte Carlo estimate. What happens to the typical error?",
                  "options": ["It shrinks by about a factor of the square root of two", "It halves exactly", "It does not change"], "answer": 0,
                  "explain_right": "Statistical error falls with the square root of the sample count.", "explain_wrong": "Error shrinks, but not linearly.", "cite": [9]}],
        "glossary": [{"term": "helix", "definition": "A spiral that advances along an axis while turning around it.", "cite": [9]}],
        "key_takeaways": ["Random numbers drive every Monte Carlo estimate.", "More samples reduce the error slowly."],
        "sources": {"chapters": ["ch02"], "read_full": []},
    }


@pytest.fixture()
def tbcourse(tb):
    work, mf = tb
    write_json(work.outline, {"book": {"title": "Computational Physics Sample", "lang": "en"}, "modules": [{
        "id": "M1", "title": "Monte Carlo", "subtitle": "Random numbers and simple estimates", "lessons": [{
            "id": "L-01", "title": "Random numbers in practice", "objectives": ["Explain why pseudo-random numbers are enough", "Run a simple counting loop"],
            "source_refs": [{"chapter": "ch02", "pages": [9, 9]}]}]}],
        "skipped": [{"chapter": "ch03", "reason": "outside this test"}]})
    return work, mf


def _check(work, lesson):
    write_json(work.drafts / "L-01.json", lesson)
    return validate.validate_lesson(work, "L-01")


# ── 7/8. small scope and packs ───────────────────────────────────────────

def test_small_scope_gives_complete_pack_with_code(tbcourse):
    work, _ = tbcourse
    meta = select.select_lesson(work, "L-01", budget=1800)
    assert meta["complete"] is True and meta["code"] == ["ch02-c01"]
    pack = (work.selections / "L-01.md").read_text()
    assert "Complete: this pack is the whole source text" in pack and "[CODE ch02-c01" in pack and "paragraph(s) omitted" not in pack


def test_gap_markers_name_what_is_missing(tb):
    work, _ = tb
    write_json(work.outline, {"book": {"title": "B", "lang": "en"}, "modules": [{"id": "M1", "title": "Monte", "subtitle": "sub title here", "lessons": [{
        "id": "L-01", "title": "Random numbers", "objectives": ["Explain random numbers well", "Use random numbers"],
        "source_refs": [{"chapter": "ch02"}]}]}]})
    meta = select.select_lesson(work, "L-01", budget=300)
    assert meta["complete"] is False
    paras = read_json(work.root / "chapters" / "ch02.paras.json")["paras"]
    om = [p for p in paras if p["kind"] == "p" and not p.get("eq")][2:5]
    hint = select._gap_hint(om, {}, 1.0, "en")
    assert hint.startswith("p.") and ":" in hint and len(hint.split(", ")) >= 3


# ── 9. citations: strict vs chapter ──────────────────────────────────────

def test_citation_outside_source_refs_but_inside_chapter_is_a_warning(tbcourse):
    work, _ = tbcourse
    # make a page-10 citation: it is in ch02 (pp.9-11) but outside source_refs pages [9, 9]
    les = _lesson()
    les["screens"][1]["blocks"][-1]["cite"] = [10]
    r = _check(work, les)
    assert not r.errors, r.errors
    assert any("inside the cited chapter but outside" in w for w in r.warnings)
    les["sources"]["read_full"] = [{"chapter": "ch02", "pages": "10-10", "reason": "needed the next page"}]
    r = _check(work, les)
    assert not any("inside the cited chapter" in w for w in r.warnings)       # pages read in full count as source pages
    les["screens"][1]["blocks"][-1]["cite"] = [_last(work.out / "x") if False else read_json(work.manifest)["chapters"][-1]["page_end"]]
    assert any("outside the chapters" in e for e in _check(work, les).errors)  # a page of ch03: still an error


# ── 6. problems with garbled math: fuzzy source + clean `shown` ──────────

def _problem_page(work):
    return next(p for p in range(9, 30) if "2-sphere" in page_text(work, p))


PROBLEM = ("6-2 The “volume” of a 2-sphere x2 + y2 = r2 (AKA a “circle”) is (1)πr2. The volume of a 3-sphere x2 + y2 + z2 = r2 is … πr3. "
           "The equation for a 4-sphere is x2+y2+z2+w2 = r2. We can guess, by extrapolation from the 2-dimensional and 3-dimensional cases, "
           "that the “volume” of a 4-sphere is απr4. Use Monte Carlo integration to estimate α.")
SHOWN = ("6-2 The “volume” of a 2-sphere $x^2 + y^2 = r^2$ (AKA a “circle”) is $\\pi r^2$. The volume of a 3-sphere $x^2 + y^2 + z^2 = r^2$ is "
         "$\\tfrac{4}{3}\\pi r^3$. The equation for a 4-sphere is $x^2+y^2+z^2+w^2 = r^2$. We can guess, by extrapolation from the 2-dimensional and "
         "3-dimensional cases, that the “volume” of a 4-sphere is $\\alpha \\pi r^4$. Use Monte Carlo integration to estimate $\\alpha$.")


def _task(page, **kw):
    return {"type": "task", "page": page, "statement": PROBLEM, "shown": SHOWN,
            "plain": "Guess how the volume of a ball in four dimensions scales with its radius and estimate the unknown constant by sampling.", **kw}


def test_task_with_garbled_math_and_clean_shown(tbcourse):
    work, _ = tbcourse
    pg = _problem_page(work)
    write_json(work.outline, {**read_json(work.outline), "modules": [{**read_json(work.outline)["modules"][0], "lessons": [{
        **read_json(work.outline)["modules"][0]["lessons"][0], "source_refs": [{"chapter": "ch02", "pages": [9, 40]}]}]}]})
    les = _lesson(extra=[_task(pg)])
    r = _check(work, les)
    assert not r.errors, r.errors
    # `shown` that rewrites the problem is rejected
    bad = _lesson(extra=[_task(pg, shown="Compute the volume of the unit ball in four dimensions by any method you like, then compare.")])
    assert any("differs from the verbatim source" in e for e in _check(work, bad).errors)
    # statement that is not on the page is rejected
    bad = _lesson(extra=[_task(pg, statement="Estimate the Reynolds number of water flowing through a pipe of known diameter and viscosity.")])
    assert any("matches the page text only" in e for e in _check(work, bad).errors)
    # inline math in `shown` is checked as LaTeX
    bad = _lesson(extra=[_task(pg, shown=SHOWN.replace("$\\alpha$", "$\\alpha^$"))])
    assert any("inline math" in e for e in _check(work, bad).errors)


def test_task_shown_renders_math(tbcourse):
    work, _ = tbcourse
    pg = _problem_page(work)
    o = read_json(work.outline)
    o["modules"][0]["lessons"][0]["source_refs"] = [{"chapter": "ch02", "pages": [9, 40]}]
    write_json(work.outline, o)
    write_json(work.drafts / "L-01.json", _lesson(extra=[_task(pg)]))
    render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    assert 'class="task-card' in html and 'data-tex="\\pi r^2"' in html and "x2 + y2" not in html.split('task-statement')[1].split("</p>")[0]


# ── code block ───────────────────────────────────────────────────────────

CODE = {"type": "code", "lang": "python", "page": 9, "code": "import random\ncount = 0\nfor i in range(100):\n    count = count+1",
        "lines": [{"at": "1", "text": "Load the module that provides random numbers."}, {"at": "2-3", "text": "Start a counter and repeat the next line one hundred times."},
                  {"at": "4", "text": "Add one to the counter on every pass."}],
        "note": "The book's listings are Python 2; this one also runs in Python 3."}


def test_code_block_verbatim_and_rendered(tbcourse):
    work, _ = tbcourse
    r = _check(work, _lesson(extra=[dict(CODE)]))
    assert not r.errors, r.errors
    bad = _lesson(extra=[{**CODE, "code": "import numpy\ncount = 0"}])
    assert any("not found verbatim" in e for e in _check(work, bad).errors)
    bad = _lesson(extra=[{**CODE, "lines": [{"at": "9", "text": "This line number does not exist in the listing."}]}])
    assert any("lines[].at" in e for e in _check(work, bad).errors)
    write_json(work.drafts / "L-01.json", _lesson(extra=[dict(CODE)]))
    render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    assert "translation-block" in html and '<span class="code-line">import random</span>' in html and "Line 2–3" in html and "Python 2" in html


def test_code_ellipsis_lines_allowed(tbcourse):
    work, _ = tbcourse
    c = {**CODE, "code": "import random\n...\n    count = count+1", "lines": [{"at": "1", "text": "Load the module that provides random numbers."}]}
    assert not _check(work, _lesson(extra=[c])).errors


# ── checked against the page image ───────────────────────────────────────

def test_formula_checked_against_image_is_book_origin(tbcourse):
    work, _ = tbcourse
    eq_page = read_json(work.root / "chapters" / "ch02.paras.json")["paras"]
    eq_page = next(p["page"] for p in eq_page if p.get("id") == "ch02-e01")
    blk = {"type": "math", "origin": "book", "cite": [eq_page], "eq": "ch02-e01", "latex": r"\sigma^2 = \frac{1}{n}\sum_i (x_i-\bar x)^2 + \Delta\hbar^{2}",
           "symbols": [{"sym": "\\sigma", "meaning": "standard deviation"}, {"sym": "\\Delta", "meaning": "a spread"}]}
    les = _lesson(extra=[blk])
    les["sources"]["read_full"] = [{"chapter": "ch02", "pages": f"{eq_page}-{eq_page}", "reason": "equation page"}]
    r = _check(work, les)
    assert any("do not appear" in e or "does not match" in e for e in r.errors)       # \hbar and \Delta are not on that page
    les["screens"][1]["blocks"][0]["checked_against"] = "image"
    r = _check(work, les)
    assert not r.errors, r.errors
    assert any("accepted because you checked it against the page image" in w for w in r.warnings)
