"""Printed-page mapping, ligature fix, task blocks, book figures and generated diagrams."""
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import ROOT, EXAMPLE, make_pdf, prepare  # noqa: E402,F401

sys.path.insert(0, str(ROOT / "scripts"))
from b2c_lib import diagrams, figtools, pagemap, render, select, validate  # noqa: E402
from b2c_lib.common import read_json, write_json  # noqa: E402
from b2c_lib.extract import _normalise  # noqa: E402


# ── printed page numbers -> PDF pages ────────────────────────────────────

@pytest.fixture(scope="module")
def off_pdf(tmp_path_factory):
    d = tmp_path_factory.mktemp("off")
    out = d / "off2.pdf"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_sample_pdf.py"), "--kind", "en", "--offset", "2", "--out", str(out)],
                   check=True, capture_output=True)
    return out


def test_pagemap_offset(off_pdf):
    m = pagemap.printed_to_pdf(off_pdf, 3, 8)
    assert m["pdf_pages"] == (5, 10) and m["offset"] == 2 and m["support"] >= 30


def test_pagemap_refuses_without_numbers(tmp_path):
    scan = make_pdf("scan", tmp_path / "scan.pdf")  # images only, no number text layer
    with pytest.raises(ValueError):
        pagemap.printed_to_pdf(scan, 1, 2)


def test_prepare_printed_pages_cli(off_pdf, tmp_path):
    out = tmp_path / "c"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "b2c.py"), "prepare", str(off_pdf), "--out", str(out),
                        "--printed-pages", "3-8", "--structure", "headings"], capture_output=True, text=True)
    assert "PDF pages 5-10" in r.stdout, r.stdout + r.stderr
    assert read_json(out / "work" / "extraction.json")["pages"] == [5, 10]


# ── ligatures and accents ────────────────────────────────────────────────

def test_ligatures_and_diaeresis_normalised():
    assert _normalise("Diﬀusion and ﬁelds, ﬂow, eﬃcient") == "Diffusion and fields, flow, efficient"
    assert _normalise("Schr¨odinger’s Equation") == "Schrödinger’s Equation"
    assert _normalise("`code` and `a") == "`code` and `a"  # backticks in code listings are left alone


# ── task blocks (book problems copied as practice) ───────────────────────

TASK = {"type": "task", "page": 4,
        "statement": "A plasma is a quasi-neutral gas of charged and neutral particles that exhibits collective behaviour.",
        "plain": "Say in your own words what makes a gas a plasma, and which property makes the charges act together.",
        "hint": "Think about the long reach of electric forces."}


def _with_block(work, block, screen=1):
    d = read_json(work.drafts / "L-01.json")
    d["screens"][screen]["blocks"].append(block)
    write_json(work.drafts / "L-01.json", d)
    return validate.validate_lesson(work, "L-01")


def test_task_block_valid_and_verbatim_checked(course):
    work, _ = course
    assert not _with_block(work, dict(TASK)).errors
    work2, _ = course
    import shutil
    shutil.copy(EXAMPLE / "L-01.json", work2.drafts / "L-01.json")
    bad = dict(TASK, statement="A plasma is a cold solid crystal of neutral atoms with nothing special going on.")
    assert any("matches the page text only" in e for e in _with_block(work2, bad).errors)
    shutil.copy(EXAMPLE / "L-01.json", work2.drafts / "L-01.json")
    assert any("plain" in e for e in _with_block(work2, dict(TASK, plain="Explain it.")).errors)


def test_task_renders_with_hint(course):
    work, _ = course
    _with_block(work, dict(TASK))
    render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    assert 'class="task-card' in html and "<details>" in html and "p.4" in html


# ── diagrams ─────────────────────────────────────────────────────────────

FLOW = {"type": "diagram", "kind": "flow", "title": "PIC loop", "caption": "One step of the cycle.", "cite": [4],
        "nodes": [{"id": "a", "label": "Weight charge to grid"}, {"id": "b", "label": "Solve the field"},
                  {"id": "c", "label": "Interpolate force"}, {"id": "d", "label": "Push particles"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}, {"from": "d", "to": "a", "label": "next step"}]}
PLOT = {"type": "diagram", "kind": "plot", "title": "Screening", "caption": "Two potentials.", "cite": [4],
        "x": {"label": "r", "min": 0.1, "max": 5}, "y": {"label": "phi", "scale": "log"},
        "series": [{"label": "1/r", "expr": "1/x"}, {"label": "exp(-r)/r", "expr": "exp(-x)/x"}],
        "points": [{"x": 1, "y": 1}]}


@pytest.mark.parametrize("spec", [FLOW, PLOT])
def test_diagram_svg_is_valid_and_deterministic(spec):
    assert diagrams.check_diagram(spec) == []
    a, b = diagrams.render_svg(spec, "t1"), diagrams.render_svg(spec, "t1")
    assert a == b
    root = ET.fromstring(a)
    assert root.tag.endswith("svg")


def test_flow_cycle_draws_return_arc_and_labels():
    svg = diagrams.render_svg(FLOW, "t2")
    assert "dg-back" in svg and "next step" in svg and svg.count("<rect") == 4


@pytest.mark.parametrize("patch,needle", [
    ({"edges": [{"from": "a", "to": "zzz"}]}, "unknown node"),
    ({"nodes": [{"id": "a", "label": "x"}]}, "2-10 nodes"),
    ({"direction": "UP"}, "direction"),
    ({"title": "uses $x^2$"}, "no $math$"),
])
def test_flow_validation(patch, needle):
    assert any(needle in e for e in diagrams.check_diagram({**FLOW, **patch}))


@pytest.mark.parametrize("expr,needle", [
    ("x^2", "write powers with **"), ("__import__('os').system('ls')", "not allowed"), ("open('f')", "not allowed"),
    ("x.real", "not allowed"), ("[1,2]", "not allowed"), ("9**9**9", "undefined or too large"), ("1/(x-x)", "undefined or too large"),
    ("sqrt(-x-10)", "undefined or too large"), ("x" * 130, "longer"),
])
def test_plot_expression_whitelist(expr, needle):
    spec = {**PLOT, "series": [{"label": "bad", "expr": expr}]}
    assert any(needle in e for e in diagrams.check_diagram(spec)), diagrams.check_diagram(spec)


def test_plot_log_scale_requires_positive_min():
    spec = {**PLOT, "x": {"label": "r", "min": 0, "max": 5, "scale": "log"}}
    assert any("log scale needs min > 0" in e for e in diagrams.check_diagram(spec))


def test_diagram_in_lesson_validates_and_renders(course):
    work, _ = course
    r = _with_block(work, dict(FLOW))
    assert not r.errors, r.errors
    r = _with_block(work, dict(PLOT))
    assert not r.errors, r.errors
    render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    assert html.count('class="diagram') >= 2 and "Illustration made for this course" in html
    assert "marker id=\"mk-d" in html


def test_lesson_without_visual_gets_warning(course):
    work, _ = course
    d = read_json(work.drafts / "L-02.json")
    for s in d["screens"]:
        s["blocks"] = [b for b in s["blocks"] if b["type"] != "diagram"]
    write_json(work.drafts / "L-02.json", d)
    r = validate.validate_lesson(work, "L-02")
    assert any("no figure or diagram" in w for w in r.warnings)


# ── book figures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fig_course(tmp_path_factory):
    d = tmp_path_factory.mktemp("fig")
    fpdf = make_pdf("fig", d / "fig.pdf")
    work, mf = prepare(fpdf, d / "c")
    return fpdf, work, mf


def test_figures_detected_and_listed(fig_course):
    _pdf, work, mf = fig_course
    assert [c["figures"] for c in mf["chapters"]] == [2, 2, 2]
    figs = figtools.list_figs(work, "ch01")
    assert [f["id"] for f in figs] == ["ch01-f01", "ch01-f02"] and figs[0]["text"].startswith("Figure 1.1")
    assert "Captions: [ch01-f01 p.1]" in (work.root / "digest_all.md").read_text()


def test_figure_crop_includes_graphic_and_axis_labels(fig_course, tmp_path):
    import pymupdf
    fpdf, work, _ = fig_course
    f = figtools.find_fig(work, "ch01-f01")
    out = figtools.crop_fig(fpdf, f, tmp_path / "f.png")
    assert out and out.exists()
    pix = pymupdf.Pixmap(str(out))
    assert 300 < pix.width < 1200 and 150 < pix.height < 600
    doc = pymupdf.open(str(fpdf))
    rect = figtools.figure_rect(doc[0], f["bbox"])
    words = {w[4] for w in doc[0].get_text("words", clip=rect)}
    assert "phi" in words and "lambda_D" in words      # y label (rotated) and x label are inside the crop
    assert "Figure" not in words                        # the caption is left to the HTML


def test_pack_lists_figures(fig_course):
    _fpdf, work, _ = fig_course
    write_json(work.outline, {"book": {"title": "F", "lang": "en"}, "modules": [{"id": "M1", "title": "Mod", "subtitle": "sub text here", "lessons": [
        {"id": "L-01", "title": "Screening of charge", "objectives": ["Explain screening of a test charge", "Describe the potential of a charge"],
         "source_refs": [{"chapter": "ch01"}]}]}]})
    meta = select.select_lesson(work, "L-01")
    assert meta["figures"] == ["ch01-f01", "ch01-f02"]
    assert "[FIG ch01-f01 · p.1] Figure 1.1." in (work.selections / "L-01.md").read_text()


def test_figure_block_checks_and_render(fig_course, tmp_path):
    _fpdf, work, _ = fig_course
    good = {"type": "figure", "fig": "ch01-f01", "page": 1, "caption": "The potential falls off quickly with distance from the charge."}
    r = validate.Result("t")
    validate._check_figure(work, good, "blk", r)
    assert not r.errors, r.errors
    for patch, needle in (({"fig": "ch01-f99"}, "no figure"), ({"page": 2}, "is on p.1"), ({"caption": "Too short."}, "own words")):
        r = validate.Result("t")
        validate._check_figure(work, {**good, **patch}, "blk", r)
        assert any(needle in e for e in r.errors), (patch, r.errors)
    ts = render.TermState({})
    html = render._block(good, ts, "en", "Figures Primer", 0)
    assert 'src="figures/ch01-f01.png"' in html and "From the book" in html and "p.1" in html


# ── course chrome: theme, contents, home, accessibility ──────────────────

from b2c_lib import ui  # noqa: E402


def _tokens(css: str, selector: str) -> dict[str, str]:
    """Custom properties declared in the first `selector { ... }` block of course.css."""
    body = css.split(selector + " {", 1)[1].split("}", 1)[0]
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", body))


@pytest.mark.parametrize("accent", sorted(ui.PENS))
def test_theme_colours_meet_wcag_aa(accent):
    css = (ROOT / "assets" / "course.css").read_text()
    light, dark = _tokens(css, ":root"), _tokens(css, ':root[data-theme="dark"]')
    for t in (light, dark):
        assert ui.contrast(t["--ink"], t["--paper"]) >= 7                       # body text
        assert ui.contrast(t["--ink-2"], t["--paper"]) >= 4.5                   # secondary text, margin notes
        assert ui.contrast(t["--ink-2"], t["--sheet"]) >= 4.5                   # secondary text on raised surfaces
        for k in ("--ok", "--bad"):
            assert ui.contrast(t[k], t["--sheet"]) >= 4.5                       # quiz feedback
    lp, dp = ui.PENS[accent]
    assert ui.contrast(lp, light["--paper"]) >= 4.5 and ui.contrast("#FFFFFF", lp) >= 4.5      # pen text; white on pen buttons
    assert ui.contrast(dp, dark["--paper"]) >= 4.5 and ui.contrast(dark["--paper"], dp) >= 4.5  # dark: pen text; dark text on pen


def test_course_has_theme_toc_home_and_a11y_hooks(course):
    work, _ = course
    render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    head = html.split("</head>")[0]
    assert "localStorage.getItem('b2c-theme')" in head and head.index("b2c-theme") < head.index("course.css")   # theme applied before first paint
    assert 'name="color-scheme"' in head and "<noscript>" in head and "book-ui.js" in head
    assert 'class="skip-link" href="#main"' in html
    assert 'id="theme-toggle"' in html and 'aria-pressed="false"' in html and 'aria-label="Dark theme"' in html
    assert 'id="nav-home"' in html and "data-toc-open" in html and 'id="toc"' in html and 'aria-controls="toc"' in html
    assert 'id="home"' in html and 'class="cover"' in html and 'class="module"' not in html.split('id="home"')[1].split("</section>")[0]
    assert 'href="#l-01"' in html and 'data-spy="module-1"' in html and 'href="#module-2"' in html      # contents lists lessons + glossary
    assert 'role="tab"' not in html and '<fieldset class="quiz-question-block"' in html and 'type="radio"' in html  # native radios
    assert 'class="gloss"' in html                                                                     # definitions sit in the margin
    css = (work.out / "course.css").read_text()
    assert ':root[data-theme="dark"]' in css and "prefers-color-scheme: dark" in css and "prefers-reduced-motion" in css and "@media print" in css
    assert css.count("--paper:") >= 3 and ":focus-visible" in css and "::selection" in css
    js = (work.out / "book-ui.js").read_text()
    assert "stopImmediatePropagation" in js and "Escape" in js and "localStorage" in js and "catch" in js and "quiz-check-btn" in js
    for gone in ("styles.css", "main.js", "book-extras.css"):                                          # third-party assets replaced
        assert not (work.out / gone).exists() and gone not in head


def test_cover_is_before_modules_and_toc_is_after_nav(course):
    work, _ = course
    render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    assert html.index('id="nav"') < html.index('id="toc"') < html.index('id="home"') < html.index('id="module-1"')
    assert html.count('id="toc"') == 1 and html.count('id="home"') == 1


def test_russian_course_chrome_is_localised(course):
    work, _ = course
    o = read_json(work.outline)
    o["book"]["lang"] = "ru"
    write_json(work.outline, o)
    render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    assert 'aria-label="Тёмная тема"' in html and "Оглавление" in html and "Начать" in html
