"""LaTeX support: draft extraction, equation ids, packs, validation, rendering. Run: make test"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import EXAMPLE, ROOT, make_pdf, prepare  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from b2c_lib import eqtools, mathtex, render, select, validate  # noqa: E402
from b2c_lib.common import read_json, write_json  # noqa: E402


# ── mathtex units ────────────────────────────────────────────────────────

def test_split_math_and_literal_dollar():
    segs = mathtex.split_math(r"Cost is \$5 and $x^2$ grows, also $\alpha_i$.")
    assert [k for k, _ in segs] == ["text", "math", "text", "math", "text"]
    assert segs[0][1].endswith("$5 and ") and segs[1][1] == "x^2"
    assert mathtex.unescaped_dollars(r"\$5 and $x$") == 2


@pytest.mark.parametrize("tex,needle", [
    (r"\frac{a}{b", "unclosed"),
    (r"\left( x", "\\left count"),
    (r"\begin{pmatrix} 1 \end{bmatrix}", "does not match"),
    (r"\begin{tikzpicture} x \end{tikzpicture}", "not supported"),
    (r"\bm{x} + 1", "not supported by KaTeX"),
    (r"\frac{a}", "needs two arguments"),
    (r"x^", "dangling"),
    (r"a % comment", "comment"),
    ("", "empty"),
    ("\\theta_0 = 1".replace("\\t", "\t"), "control character"),
    ("\x0crac{a}{b}", "control character"),
])
def test_check_latex_rejects(tex, needle):
    assert any(needle in e for e in mathtex.check_latex(tex)), mathtex.check_latex(tex)


def test_check_latex_accepts_good_formulas():
    for tex in (r"\lambda_D = \sqrt{\frac{\epsilon_0 k_B T_e}{n e^{2}}}", r"\omega_p^2 = \frac{n e^2}{\epsilon_0 m}",
                r"\begin{aligned} a &= b \\ c &= d \end{aligned}", r"\frac12 m v^2", r"\sqrt x", r"\int_0^\infty e^{-x}\,dx"):
        assert mathtex.check_latex(tex) == [], tex


def test_grounding_atoms():
    s, miss = mathtex.grounding(r"\lambda_D = \sqrt{\frac{\epsilon_0}{n}}", "λD = √(ε0 kB Te / (n e2))")
    assert s == 1.0 and not miss
    s, miss = mathtex.grounding(r"E = \hbar \omega + \sigma", "The plasma frequency scales with density.")
    assert s == 0.0 and "ω" in miss
    assert mathtex.grounding(r"a + b", "x")[0] is None  # nothing distinctive to verify


def test_draft_from_spans_uses_geometry():
    sp = [{"text": "x", "size": 11, "origin": (0, 100)}, {"text": "2", "size": 7.5, "origin": (6, 95)},
          {"text": " + y", "size": 11, "origin": (10, 100)}, {"text": "i", "size": 7.5, "origin": (20, 103)}]
    assert mathtex.spans_to_tex(sp) == "x^{2} + y_{i}"
    assert mathtex.text_to_tex("ω² = ωp² ≈ √(a b)") .startswith(r"\omega ^{2}")


# ── extraction, equation ids, packs ──────────────────────────────────────

def test_equations_detected_with_numbers_and_sub_superscripts(course):
    work, mf = course
    ch = {c["id"]: c for c in mf["chapters"]}
    assert ch["ch03"]["equations"] == 9 and ch["ch03"]["equations_numbered"] == 9
    eq = eqtools.find_eq(work, "ch03-e01")
    assert eq["page"] == 4 and eq["num"] == "1.1" and eq["bbox"][2] > eq["bbox"][0]
    assert eq["tex"] == r"\lambda_{D} = \sqrt{(\epsilon_{0} k_{B} T_{e} / (n e^{2}))}"
    assert "(1.1)" not in eq["tex"]


def test_equations_are_not_prose_and_not_in_word_count(course):
    work, mf = course
    md = next(work.chapters.glob("ch03-*.md")).read_text()
    assert "[EQ ch03-e01 · p.4 · eq.(1.1)] draft: $" in md
    d = (work.digests / "ch03.md").read_text()
    assert "Equations: 9 display (9 numbered)" in d and "ch03-e01" in d
    assert all("\\lambda" not in s for s in d.split("Key sentences:")[1].split("Terms")[0].splitlines())


def test_pack_carries_equations_with_verify_note(course):
    work, _ = course
    meta = select.select_lesson(work, "L-01", budget=1500)
    assert "ch03-e01" in meta["equations"]
    pack = (work.selections / "L-01.md").read_text()
    assert "[EQ ch03-e01" in pack and "verify with `b2c.py eq" in pack
    assert meta["tokens"] <= 1580


def test_equation_image_crop_and_page_image(course, pdf):
    work, _ = course
    eq = eqtools.find_eq(work, "ch03-e01")
    png = eqtools.crop_eq(work, pdf, eq)
    assert png and png.exists() and png.read_bytes()[:4] == b"\x89PNG"
    assert eqtools.page_image(work, pdf, 4).exists()


# ── validation ───────────────────────────────────────────────────────────

def _mut(work, lid, fn):
    d = read_json(work.drafts / f"{lid}.json")
    fn(d)
    write_json(work.drafts / f"{lid}.json", d)
    return validate.validate_lesson(work, lid)


def _math(d, lid_screen=1):
    return next(b for b in d["screens"][lid_screen]["blocks"] if b["type"] == "math")


def test_example_math_lessons_validate(course):
    work, _ = course
    for r in validate.validate_course(work):
        assert not r.errors, (r.scope, r.errors)


def test_validator_rejects_broken_latex_in_block_and_inline(course):
    work, _ = course
    r = _mut(work, "L-01", lambda d: _math(d).__setitem__("latex", r"\frac{a}{b"))
    assert any("unclosed" in e for e in r.errors)
    work2 = course[0]
    shutil.copy(EXAMPLE / "L-01.json", work2.drafts / "L-01.json")
    r = _mut(work2, "L-01", lambda d: d["screens"][0]["blocks"][0].__setitem__("text", r"A [[plasma]] has $\bm{x$ and more [[plasma]]", ) or d["screens"][0]["blocks"][0].__setitem__("cite", [4]))
    assert any("inline math" in e or "unbalanced" in e for e in r.errors)


def test_validator_rejects_fabricated_formula(course):
    work, _ = course
    r = _mut(work, "L-01", lambda d: (_math(d).__setitem__("latex", r"E = \hbar \omega + \sigma^{2}"), _math(d).pop("eq")))
    assert any("do not appear on cited" in e for e in r.errors)


def test_derived_formula_is_allowed_and_flagged(course):
    work, _ = course
    r = _mut(work, "L-01", lambda d: (_math(d).__setitem__("latex", r"E = \hbar \omega"), _math(d).pop("eq"),
                                      _math(d).__setitem__("origin", "derived"), _math(d).__setitem__("caption", "Derived here from the screening idea.")))
    assert not r.errors, r.errors


def test_validator_checks_eq_id_page_and_content(course):
    work, _ = course
    r = _mut(work, "L-01", lambda d: _math(d).__setitem__("eq", "ch03-e99"))
    assert any("ch03-e99" in e for e in r.errors)
    shutil.copy(EXAMPLE / "L-01.json", work.drafts / "L-01.json")
    r = _mut(work, "L-01", lambda d: _math(d).__setitem__("eq", "ch03-e05"))  # on p.7, cite is [4]
    assert any("not in cite" in e for e in r.errors)


def test_validator_requires_symbols_and_warns_on_unnamed_greek(course):
    work, _ = course
    r = _mut(work, "L-01", lambda d: _math(d).__setitem__("symbols", []))
    assert any("symbols" in e for e in r.errors)
    shutil.copy(EXAMPLE / "L-01.json", work.drafts / "L-01.json")
    r = _mut(work, "L-01", lambda d: _math(d).__setitem__("symbols", [{"sym": "n", "meaning": "density"}]))
    assert any("\\lambda" in w for w in r.warnings)


def test_glossary_tooltips_cannot_hold_math(course):
    work, _ = course
    r = _mut(work, "L-01", lambda d: d["glossary"][0].__setitem__("definition", "Scale $\\lambda_D$ of screening in a plasma."))
    assert any("plain text" in e for e in r.errors)


# ── rendering ────────────────────────────────────────────────────────────

def test_render_math_course(course):
    work, _ = course
    info = render.render(work, work.out)
    assert info["math"] is True
    html = (work.out / "index.html").read_text()
    assert 'class="math-block' in html and 'data-display="1"' in html and "katex@0.16" in html and "book-math.js" in html
    assert 'data-tex="\\lambda_D"' in html          # symbol table
    assert "$2 v_\\perp$" not in html or "data-explanation-right" in html
    assert (work.out / "book-math.js").exists()
    assert "$\\lambda_D$</span>" in html            # fallback text inside the span if KaTeX is unreachable


def test_render_without_math_has_no_katex(course):
    work, _ = course
    for lid in ("L-01", "L-02"):
        d = read_json(work.drafts / f"{lid}.json")
        for s in d["screens"]:
            s["blocks"] = [b for b in s["blocks"] if b["type"] != "math"]
            for b in s["blocks"]:
                if b["type"] == "quote":
                    b["meaning"] = b["meaning"].replace("$\\lambda_D$ ", "").replace("$\\lambda_D$", "")
        d["quiz"][0]["question"] = d["quiz"][0]["question"].replace("$\\lambda_D$ ", "").replace("$v_\\perp$ ", "").replace("$r_L$ ", "")
        d["quiz"][0]["explain_right"] = "The Larmor radius grows with the particle speed, so double speed gives a wider circle."
        write_json(work.drafts / f"{lid}.json", d)
    info = render.render(work, work.out)
    html = (work.out / "index.html").read_text()
    assert info["math"] is False and "katex" not in html and not (work.out / "book-math.js").exists()
