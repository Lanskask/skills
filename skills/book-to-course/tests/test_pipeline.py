"""End-to-end tests on synthetic books (see scripts/make_sample_pdf.py). Run: make test"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from b2c_lib import clean, digest, extract, render, select, split, structure, validate  # noqa: E402
from b2c_lib.common import Work, est_tokens, read_json, write_json  # noqa: E402

EXAMPLE = ROOT / "templates" / "example"


def make_pdf(kind: str, path: Path) -> Path:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_sample_pdf.py"), "--kind", kind, "--out", str(path)],
                   check=True, capture_output=True)
    return path


def prepare(pdf: Path, out: Path, pages=None, mode="auto", ids=None) -> tuple[Work, dict]:
    work = Work(out)
    work.mkdirs()
    total = extract.page_count(pdf)
    pages = pages or (1, total)
    ex = extract.extract(pdf, work, pages)
    ex["pdf"] = str(pdf)
    write_json(work.root / "extraction.json", ex)
    clean.clean(work, pages)
    structure.detect(pdf, work, pages, mode=mode)
    mf = split.split(pdf, work, pages, ex, chapter_ids=ids)
    digest.digest_all(work)
    return work, mf


@pytest.fixture(scope="session")
def pdfs(tmp_path_factory):
    d = tmp_path_factory.mktemp("pdfs")
    return {k: make_pdf(k, d / f"{k}.pdf") for k in ("en", "noout", "scan", "ru")}


@pytest.fixture()
def en(pdfs, tmp_path):
    return prepare(pdfs["en"], tmp_path / "c")


def test_outline_structure_and_page_ranges(en):
    work, mf = en
    assert mf["structure"] == {"source": "outline", "confidence": "high"}
    ch = [c for c in mf["chapters"] if c["kind"] == "chapter"]
    assert [c["title"] for c in ch][0] == "Chapter 1. Introduction to Plasma"
    assert len(ch) == 5
    # contiguous, non-overlapping chapter page ranges
    for a, b in zip(ch, ch[1:]):
        assert a["page_end"] + 1 == b["page_start"]
    assert [c["kind"] for c in mf["chapters"] if c["kind"] != "chapter"] == ["front", "front", "back"]
    assert all(len(c["sections"]) == 3 for c in ch)


def test_headers_footers_and_page_numbers_removed(en):
    work, _ = en
    txt = "\n".join((p).read_text() for p in work.chapters.glob("*.md"))
    assert "All rights reserved" not in txt
    assert "Plasma Simulation Primer" not in txt  # running header
    rep = read_json(work.root / "clean_report.json")
    assert rep["page_numbers_removed"] >= 30
    assert "­" not in txt and "\xa0" not in txt


def test_no_hyphen_breaks_left(en):
    work, _ = en
    txt = (next(work.chapters.glob("ch03-*.md"))).read_text()
    assert "behaviour" in txt and "surrounding" in txt  # were split across lines in the PDF


def test_digest_budget_and_content(en):
    work, mf = en
    for c in mf["chapters"]:
        if c["kind"] == "chapter":
            d = (work.digests / f"{c['id']}.md").read_text()
            assert est_tokens(d) <= 480
            assert "Key sentences:" in d and "Sections:" in d and "Debye" in d or c["id"] != "ch03"
    allmd = (work.root / "digest_all.md").read_text()
    assert est_tokens(allmd) < 0.15 * mf["totals"]["est_tokens"]


def test_digest_is_deterministic(pdfs, tmp_path):
    w1, _ = prepare(pdfs["en"], tmp_path / "a")
    w2, _ = prepare(pdfs["en"], tmp_path / "b")
    assert (w1.root / "digest_all.md").read_text().replace(str(tmp_path / "a"), "") == \
        (w2.root / "digest_all.md").read_text().replace(str(tmp_path / "b"), "")


def test_page_range_scope(pdfs, tmp_path):
    work, mf = prepare(pdfs["en"], tmp_path / "r", pages=(11, 17))
    ids = [c["id"] for c in mf["chapters"]]
    assert ids == ["ch04"]  # id is stable: same id as in the whole-book run
    assert mf["chapters"][0]["page_start"] == 11 and mf["chapters"][0]["page_end"] == 17
    assert len(list(work.pages.glob("*.json"))) == 7


def test_range_starting_mid_chapter_gets_continued_node(pdfs, tmp_path):
    _, mf = prepare(pdfs["en"], tmp_path / "m", pages=(13, 20))
    titles = [c["title"] for c in mf["chapters"]]
    assert titles[0].endswith("(continued)") and "Charged Particle Motion" in titles[0]


def test_heading_fallback_without_outline(pdfs, tmp_path):
    _, mf = prepare(pdfs["noout"], tmp_path / "h")
    assert mf["structure"]["source"] == "headings"
    ch = [c for c in mf["chapters"] if c["kind"] == "chapter"]
    assert len(ch) == 5 and ch[1]["title"].startswith("Chapter 2")
    assert all(len(c["sections"]) == 3 for c in ch)


def test_chunk_fallback(pdfs, tmp_path):
    _, mf = prepare(pdfs["noout"], tmp_path / "k", mode="chunks")
    assert mf["structure"]["source"] == "chunks" and mf["structure"]["confidence"] == "low"


def test_russian_book(pdfs, tmp_path):
    work, mf = prepare(pdfs["ru"], tmp_path / "ru")
    assert mf["book"]["lang"] == "ru"
    assert len(mf["chapters"]) == 3
    d = (work.digests / "ch02.md").read_text()
    assert "Definitions:" in d and "столкновен" in d.lower()


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_ocr_fallback(pdfs, tmp_path):
    work, mf = prepare(pdfs["scan"], tmp_path / "s")
    assert mf["extraction"]["ocr_pages"] == [1, 2, 3]
    txt = " ".join(p.read_text() for p in work.chapters.glob("*.md")).lower()
    assert "plasma" in txt and "debye" in txt


def test_select_pack_is_small_and_flags_thin_coverage(en):
    work, mf = en
    shutil.copy(EXAMPLE / "outline.json", work.outline)
    meta = select.select_lesson(work, "L-01", budget=1200)
    assert meta["tokens"] <= 1300 and meta["pages"][0] >= 4 and meta["pages"][1] <= 7
    assert meta["source_tokens_available"] > meta["tokens"]
    o = read_json(work.outline)
    o["modules"][0]["lessons"][0]["objectives"] = ["Derive the quark gluon confinement bag model", "Explain baryon asymmetry"]
    write_json(work.outline, o)
    meta = select.select_lesson(work, "L-01", budget=1200)
    assert meta["needs_more"] is True


def _course(en):
    work, _ = en
    shutil.copy(EXAMPLE / "outline.json", work.outline)
    for f in EXAMPLE.glob("L-*.json"):
        shutil.copy(f, work.drafts / f.name)
    return work


def test_example_course_validates_and_renders(en, tmp_path):
    work = _course(en)
    results = validate.validate_course(work)
    assert all(not r.errors for r in results), [r.errors for r in results]
    info = render.render(work, work.out)
    assert info["lessons"] == 2 and info["glossary_terms"] == 6
    html = (work.out / "index.html").read_text()

    class P(HTMLParser):
        void = {"meta", "link", "br", "img", "input", "hr"}

        def __init__(self):
            super().__init__()
            self.stack, self.errs = [], []

        def handle_starttag(self, t, a):
            if t not in self.void:
                self.stack.append(t)

        def handle_endtag(self, t):
            if not self.stack or self.stack.pop() != t:
                self.errs.append(t)

    p = P()
    p.feed(html)
    assert not p.errs and not p.stack
    assert html.count('class="module"') == 2 and 'class="gloss"' in html and "src-ref" in html
    assert "COURSE_TITLE" not in html and "ACCENT_" not in html and "NAV_DOTS" not in html
    for f in ("course.css", "book-ui.js"):  # the skill's own assets, copied as they are
        assert (work.out / f).read_bytes() == (ROOT / "assets" / f).read_bytes()


def _mutate(work, lesson, fn):
    d = read_json(work.drafts / f"{lesson}.json")
    fn(d)
    write_json(work.drafts / f"{lesson}.json", d)
    return validate.validate_lesson(work, lesson)


def test_validator_catches_bad_citation(en):
    work = _course(en)
    r = _mutate(work, "L-01", lambda d: d["screens"][0]["blocks"][0].__setitem__("cite", [30]))
    assert any("outside the chapters this lesson cites" in e for e in r.errors)


def test_validator_catches_long_and_fabricated_quotes(en):
    work = _course(en)
    long_q = "The Debye length is the distance over which a charge imbalance is screened by the surrounding particles and more words here to clearly exceed the limit of words"
    r = _mutate(work, "L-01", lambda d: d["screens"][1]["blocks"][0].__setitem__("text", long_q))
    assert any("max 25" in e for e in r.errors)
    r = _mutate(work, "L-01", lambda d: d["screens"][1]["blocks"][0].__setitem__("text", "The Debye length is the distance to the nearest star"))
    assert any("not found verbatim" in e for e in r.errors)


def test_validator_catches_missing_glossary_objective_and_quiz(en):
    work = _course(en)
    r = _mutate(work, "L-01", lambda d: d["glossary"].pop(0))
    assert any("no glossary entry" in e for e in r.errors)
    work = _course(en)
    r = _mutate(work, "L-02", lambda d: d["screens"][1].__setitem__("covers", [1]))
    assert any("objective 2" in e for e in r.errors)
    work = _course(en)
    r = _mutate(work, "L-02", lambda d: d["quiz"][0].__setitem__("answer", 7))
    assert any("answer index" in e for e in r.errors)


def test_validator_catches_verbatim_copy_outside_quote(en):
    work = _course(en)
    copied = ("A plasma is a quasi-neutral gas of charged and neutral particles that exhibits collective "
              "behaviour and more")
    r = _mutate(work, "L-01", lambda d: d["screens"][0]["blocks"][0].__setitem__("text", copied))
    assert any("copied from the source" in x for x in r.errors + r.warnings)


def test_validator_catches_uncovered_chapter(en):
    work = _course(en)
    o = read_json(work.outline)
    o["skipped"] = o["skipped"][:-1]
    write_json(work.outline, o)
    r = validate.validate_outline(work)
    assert any("coverage: ch07" in e for e in r.errors)


def test_validator_catches_bad_outline_refs(en):
    work = _course(en)
    o = read_json(work.outline)
    o["modules"][0]["lessons"][0]["source_refs"][0]["pages"] = [4, 99]
    o["modules"][0]["lessons"][1]["source_refs"][0]["chapter"] = "ch42"
    write_json(work.outline, o)
    errs = validate.validate_outline(work).errors
    assert any("outside ch03" in e for e in errs) and any("ch42" in e for e in errs)


def test_full_read_is_logged(en):
    work, _ = en
    txt = select.read_range(work, "ch03", (4, 4), max_tokens=500)
    assert "<!-- p.4 -->" in txt
    assert validate.usage_summary(work)["full_reads"] == 1
