#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pymupdf>=1.24"]
# ///
"""book-to-course CLI. Every command is deterministic and makes no LLM calls.

  outline   PDF                                            list chapter ids + pages from the PDF bookmarks (instant)
  find      PDF "Heading" ["Heading" ...]                      where headings are (PDFs without bookmarks)
  pagemap   PDF --printed 123-153 [--anchor "Heading"]                          printed page numbers -> PDF page numbers
  prepare   PDF --out DIR [--pages A-B | --printed-pages A-B | --chapters 3-5]   extract+clean+structure+split+digest in one go
  extract | clean | structure | split | digest              individual stages (for debugging / re-runs)
  eq        --out DIR --id ch04-e03 [--image] | --chapter ch04 --list   machine-drafted LaTeX of a formula (+ picture)
  fig       --out DIR --id ch03-f02 [--image] | --chapter ch03 --list   book figure captions (+ cropped picture)
  page-image --out DIR --page N                           render one PDF page as PNG (for scanned/complex formulas)
  select    --out DIR --lesson L-01 [--budget 1800]         Pass-2 passage pack for one lesson
  read      --out DIR --chapter ch03 [--pages 44-46]        explicit full-text fallback (logged)
  validate  --out DIR [--stage outline|lesson|course] [--lesson L-01]
  render    --out DIR [--partial]                           drafts -> HTML course (+ index.html)
  status    --out DIR                                       what is done / what is next (resumability)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from b2c_lib.common import Work, parse_range, read_json, write_json  # noqa: E402


def _chapter_ids(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    nums = []
    for part in spec.split(","):
        m = re.fullmatch(r"\s*(?:ch)?(\d+)\s*(?:[-–]\s*(?:ch)?(\d+))?\s*", part)
        if not m:
            raise SystemExit(f"bad --chapters {spec!r}; use e.g. 3-5 or ch03,ch07")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        nums += list(range(a, b + 1))
    return nums


def cmd_prepare(a) -> None:
    from b2c_lib import clean, digest, extract, split, structure

    pdf, work = Path(a.pdf).expanduser().resolve(), Work(Path(a.out).expanduser())
    if not pdf.exists():
        raise SystemExit(f"no such file: {pdf}")
    if a.pages and a.chapters:
        raise SystemExit("use either --pages or --chapters, not both")
    total = extract.page_count(pdf)
    pages = parse_range(a.pages) or (1, total)
    if a.printed_pages:
        from b2c_lib import pagemap
        if a.pages or a.chapters:
            raise SystemExit("use only one of --pages, --printed-pages, --chapters")
        try:
            m = pagemap.printed_to_pdf(pdf, *parse_range(a.printed_pages), anchor=a.anchor)
        except ValueError as e:
            raise SystemExit(f"--printed-pages: {e}")
        pages = m["pdf_pages"]
        print(f"printed pages {a.printed_pages} = PDF pages {pages[0]}-{pages[1]} (offset {m['offset']:+d}, "
              f"seen on {m['support']} of {m['of']} nearby pages). Whole chapters wanted? Prefer --chapters.")
    ids = None
    if a.chapters:
        nums = _chapter_ids(a.chapters)
        ids = {f"ch{n:02d}" for n in nums}
        outl = structure.outline_chapters(pdf)
        if outl:
            sel = [c for c in outl if c["id"] in ids]
            if not sel:
                raise SystemExit(f"no outline chapters match {a.chapters}; known: {[c['id'] + ' ' + c['title'] for c in outl][:12]}")
            pages = (min(c["page_start"] for c in sel), max(c["page_end"] for c in sel))
            print(f"--chapters {a.chapters} -> pages {pages[0]}-{pages[1]} (from PDF outline)")
        else:
            print("no usable PDF outline: processing the whole book, then keeping only the requested chapter ids")
    pages = (max(1, pages[0]), min(total, pages[1]))
    work.mkdirs()
    ex = extract.extract(pdf, work, pages, ocr=a.ocr, ocr_lang=a.ocr_lang)
    ex["pdf"] = str(pdf)
    write_json(work.root / "extraction.json", ex)
    cl = clean.clean(work, pages)
    st = structure.detect(pdf, work, pages, mode=a.structure, chunk_pages=a.chunk_pages)
    mf = split.split(pdf, work, pages, ex, chapter_ids=ids)
    dg = digest.digest_all(work, budget=a.digest_budget)
    print(json.dumps({
        "pages": list(pages), "ocr_pages": len(ex["ocr_pages"]), "empty_pages": len(ex["empty_pages"]),
        "removed_header_footer_lines": cl["lines_removed"],
        "structure": f"{st['source']} ({st['confidence']})",
        "chapters": [f"{c['id']} {c['kind']} pp.{c['page_start']}-{c['page_end']} {c['words']}w" for c in mf["chapters"]],
        "book_tokens_est": mf["totals"]["est_tokens"], **dg,
        "next": f"Pass 1: read {work.root / 'digest_all.md'} only, then write {work.outline}",
    }, ensure_ascii=False, indent=2))
    if mf["totals"]["est_tokens"] < 25000:
        print(f"NOTE: this scope is small (~{mf['totals']['est_tokens']:,} tokens). Reading it directly costs about the same as digests + packs; "
              f"packs of lessons this small come out complete (no gaps). The skill still adds citations, validation, figures and rendering.", file=sys.stderr)
    if st["confidence"] == "low":
        print("WARNING: low-confidence structure; check work/structure.json, or re-run with --structure headings|chunks / --chunk-pages N",
              file=sys.stderr)


def _scope(work: Work) -> tuple[Path, tuple[int, int]]:
    ex = read_json(work.root / "extraction.json")
    return Path(ex["pdf"]), tuple(ex["pages"])


def cmd_outline(a) -> None:
    from b2c_lib import structure
    pdf = Path(a.pdf).expanduser().resolve()
    chs = structure.outline_chapters(pdf)
    if not chs:
        print("no usable PDF outline. Find chapters with: b2c.py find PDF \"Chapter title\" ...  then use --pages A-B, or "
              "--printed-pages A-B [--anchor \"Chapter title\"]")
    for c in chs:
        print(f"{c['id']:<6} {c['kind']:<8} pp.{c['page_start']}-{c['page_end']:<5} {c['title']}")


def cmd_eq(a) -> None:
    from b2c_lib import eqtools
    work = Work(Path(a.out))
    pdf, _ = _scope(work)
    if a.list:
        for e in eqtools.list_eqs(work, a.chapter):
            print(f"{e['id']:<11} p.{e['page']:<5} {('(' + e['num'] + ')') if e.get('num') else '':<8} ${e['tex']}$")
        return
    e = eqtools.find_eq(work, a.id)
    print(f"{e['id']} · p.{e['page']}" + (f" · eq.({e['num']})" if e.get("num") else ""))
    print(f"source text : {e['text']}")
    print(f"LaTeX draft : {e['tex']}   (machine-built; verify against the image)")
    if a.image:
        img = eqtools.crop_eq(work, pdf, e)
        print(f"image       : {img}  (open it with the Read tool)" if img else
              f"no geometry for this page (OCR); use: b2c.py page-image --out {a.out} --page {e['page']}")


def cmd_fig(a) -> None:
    from b2c_lib import figtools
    work = Work(Path(a.out))
    pdf, _ = _scope(work)
    if a.list:
        for f in figtools.list_figs(work, a.chapter):
            print(f"{f['id']:<11} p.{f['page']:<5} {f['text'][:90]}")
        return
    f = figtools.find_fig(work, a.id)
    print(f"{f['id']} · p.{f['page']}\ncaption: {f['text']}")
    if a.image:
        img = figtools.crop_fig(pdf, f, work.root / "fig" / f"{f['id']}.png")
        print(f"image  : {img}  (open it with the Read tool)" if img else
              f"no separable graphics found: use `b2c.py page-image --out {a.out} --page {f['page']}`")


def cmd_page_image(a) -> None:
    from b2c_lib import eqtools
    work = Work(Path(a.out))
    print(eqtools.page_image(work, _scope(work)[0], a.page, a.dpi))


def cmd_find(a) -> None:
    from b2c_lib import pagemap
    pdf = Path(a.pdf).expanduser().resolve()
    for q, hits in pagemap.find_headings(pdf, a.query).items():
        print(f"{q!r}:" + ("" if hits else "  not found"))
        for h in hits:
            print(f"   PDF p.{h['pdf_page']:<5} {'heading-like' if h['heading_like'] else 'plain text  '}  size {h['size']} (body {h['body']})  {h['text']}")


def cmd_pagemap(a) -> None:
    from b2c_lib import pagemap
    pdf = Path(a.pdf).expanduser().resolve()
    a0, b0 = parse_range(a.printed)
    try:
        m = pagemap.printed_to_pdf(pdf, a0, b0, anchor=a.anchor)
    except ValueError as e:
        raise SystemExit(str(e))
    print(f"printed {a0}-{b0} = PDF pages {m['pdf_pages'][0]}-{m['pdf_pages'][1]} "
          f"(offset {m['offset']:+d}, " + (f"via {m['via']}" if m.get("via") else f"seen on {m['support']} of {m['of']} nearby pages") + ")")


def cmd_extract(a) -> None:
    from b2c_lib import extract
    pdf, work = Path(a.pdf).resolve(), Work(Path(a.out))
    work.mkdirs()
    pages = parse_range(a.pages) or (1, extract.page_count(pdf))
    ex = extract.extract(pdf, work, pages, ocr=a.ocr, ocr_lang=a.ocr_lang)
    ex["pdf"] = str(pdf)
    write_json(work.root / "extraction.json", ex)
    print(json.dumps(ex))


def cmd_clean(a) -> None:
    from b2c_lib import clean
    work = Work(Path(a.out))
    print(json.dumps(clean.clean(work, _scope(work)[1])["lines_removed"]))


def cmd_structure(a) -> None:
    from b2c_lib import structure
    work = Work(Path(a.out))
    pdf, pages = _scope(work)
    st = structure.detect(pdf, work, pages, mode=a.mode, chunk_pages=a.chunk_pages)
    for n in st["nodes"]:
        print(f"{'  ' * (n['level'] - 1)}{n['id']:<9} {n['kind']:<8} p.{n['page']:<5} {n['title']}")
    print(f"source={st['source']} confidence={st['confidence']}")


def cmd_split(a) -> None:
    from b2c_lib import split
    work = Work(Path(a.out))
    pdf, pages = _scope(work)
    mf = split.split(pdf, work, pages, read_json(work.root / "extraction.json"))
    print(json.dumps(mf["totals"]))


def cmd_digest(a) -> None:
    from b2c_lib import digest
    print(json.dumps(digest.digest_all(Work(Path(a.out)), budget=a.budget)))


def cmd_select(a) -> None:
    from b2c_lib import select
    work = Work(Path(a.out))
    lessons = [a.lesson] if a.lesson else [l["id"] for m in read_json(work.outline)["modules"] for l in m["lessons"]]
    for lid in lessons:
        meta = select.select_lesson(work, lid, budget=a.budget)
        print(f"{lid}: ~{meta['tokens']} tok (of ~{meta['source_tokens_available']}), coverage {meta['term_coverage']:.0%}, "
              f"needs_more={meta['needs_more']} -> {work.selections / (lid + '.md')}")
        if meta["needs_more"]:
            print("   reasons: " + "; ".join(meta["reasons"]))


def cmd_read(a) -> None:
    from b2c_lib import select
    sys.stdout.write(select.read_range(Work(Path(a.out)), a.chapter, parse_range(a.pages), a.max_tokens))


def cmd_validate(a) -> None:
    from b2c_lib import validate
    work = Work(Path(a.out))
    if a.stage == "outline":
        results = [validate.validate_outline(work)]
    elif a.stage == "lesson":
        ids = [a.lesson] if a.lesson else [f.stem for f in sorted(work.drafts.glob("L-*.json"))]
        results = [validate.validate_lesson(work, i) for i in ids]
    else:
        results = validate.validate_course(work)
    rep = validate.write_report(work, results)
    for r in results:
        mark = "FAIL" if r.errors else "ok  "
        print(f"[{mark}] {r.scope}: {len(r.errors)} error(s), {len(r.warnings)} warning(s)")
        for e in r.errors[:15]:
            print(f"   ERROR {e}")
        for w in r.warnings[:8]:
            print(f"   warn  {w}")
    print(f"report -> {work.report}")
    sys.exit(0 if rep["ok"] else 1)


def cmd_render(a) -> None:
    from b2c_lib import render, validate
    work = Work(Path(a.out))
    if not a.skip_validate:
        results = validate.validate_course(work) if not a.partial else \
            [validate.validate_outline(work)] + [validate.validate_lesson(work, f.stem) for f in sorted(work.drafts.glob("L-*.json"))]
        bad = [r for r in results if r.errors and r.scope != "course" or (r.scope == "course" and r.errors and not a.partial)]
        if bad:
            for r in bad:
                print(f"[FAIL] {r.scope}: " + "; ".join(r.errors[:3]))
            raise SystemExit("validation failed; fix the drafts (or use --skip-validate for a preview)")
    info = render.render(work, Path(a.out), partial=a.partial)
    print(json.dumps(info, ensure_ascii=False))


def cmd_status(a) -> None:
    work = Work(Path(a.out))
    print(f"manifest : {'yes' if work.manifest.exists() else 'NO  -> run prepare'}")
    print(f"digests  : {'yes' if (work.root / 'digest_all.md').exists() else 'NO'}")
    print(f"outline  : {'yes' if work.outline.exists() else 'NO  -> Pass 1'}")
    if work.outline.exists():
        from b2c_lib import validate
        outline = read_json(work.outline)
        todo = []
        for m, l in validate._lessons(outline):
            sel = (work.selections / f"{l['id']}.md").exists()
            dr = (work.drafts / f"{l['id']}.json").exists()
            ok = dr and not validate.validate_lesson(work, l["id"]).errors
            state = "validated" if ok else "draft-invalid" if dr else "pack-ready" if sel else "todo"
            print(f"  {l['id']}  {state:<14} {l['title']}")
            if not ok:
                todo.append(l["id"])
        print("next:", f"write/fix {todo[0]}" if todo else "render")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, pdf=False):
        p = sub.add_parser(name)
        if pdf:
            p.add_argument("pdf")
        p.add_argument("--out", required=True, help="course directory (work files go in <out>/work)")
        p.set_defaults(fn=fn)
        return p

    p = add("prepare", cmd_prepare, pdf=True)
    p.add_argument("--pages", help="PDF page range, e.g. 120-180")
    p.add_argument("--chapters", help="chapter ids, e.g. 3-5 (uses the PDF outline to find pages)")
    p.add_argument("--anchor", help="with --printed-pages: heading text that opens the range (when margin page numbers are unreadable)")
    p.add_argument("--printed-pages", help="page range as printed in the book's contents, e.g. 123-153 (mapped to PDF pages)")
    p.add_argument("--ocr", choices=["auto", "off", "force"], default="auto")
    p.add_argument("--ocr-lang", default=None, help="tesseract langs, default eng+rus when installed")
    p.add_argument("--structure", choices=["auto", "outline", "headings", "chunks"], default="auto")
    p.add_argument("--chunk-pages", type=int, default=20)
    p.add_argument("--digest-budget", type=int, default=450, help="max tokens per chapter digest")
    p = add("eq", cmd_eq)
    p.add_argument("--id", help="equation id, e.g. ch04-e03")
    p.add_argument("--chapter", help="with --list: chapter id")
    p.add_argument("--list", action="store_true", help="list drafted equations of a chapter")
    p.add_argument("--image", action="store_true", help="also crop the equation picture from the PDF")
    p = add("fig", cmd_fig)
    p.add_argument("--id", help="figure id, e.g. ch03-f02")
    p.add_argument("--chapter", help="with --list: chapter id")
    p.add_argument("--list", action="store_true", help="list figure captions of a chapter")
    p.add_argument("--image", action="store_true", help="crop the figure picture from the PDF to look at it")
    p = add("page-image", cmd_page_image)
    p.add_argument("--page", type=int, required=True)
    p.add_argument("--dpi", type=int, default=110)
    p = sub.add_parser("pagemap", help="convert printed page numbers to PDF page numbers (no extraction)")
    p.add_argument("pdf")
    p.add_argument("--printed", required=True, help="e.g. 123-153")
    p.add_argument("--anchor", help="heading text that opens the range (fallback when margin page numbers are unreadable)")
    p.set_defaults(fn=cmd_pagemap)
    p = sub.add_parser("find", help="find where headings appear (PDFs without bookmarks)")
    p.add_argument("pdf")
    p.add_argument("query", nargs="+", help='heading texts, e.g. "Monte Carlo Techniques"')
    p.set_defaults(fn=cmd_find)
    p = sub.add_parser("outline", help="list chapter ids/pages from the PDF outline (no extraction)")
    p.add_argument("pdf")
    p.set_defaults(fn=cmd_outline)
    p = add("extract", cmd_extract, pdf=True)
    p.add_argument("--pages")
    p.add_argument("--ocr", choices=["auto", "off", "force"], default="auto")
    p.add_argument("--ocr-lang", default=None)
    add("clean", cmd_clean)
    p = add("structure", cmd_structure)
    p.add_argument("--mode", choices=["auto", "outline", "headings", "chunks"], default="auto")
    p.add_argument("--chunk-pages", type=int, default=20)
    add("split", cmd_split)
    p = add("digest", cmd_digest)
    p.add_argument("--budget", type=int, default=450)
    p = add("select", cmd_select)
    p.add_argument("--lesson", help="lesson id; omit for all lessons")
    p.add_argument("--budget", type=int, default=1800)
    p = add("read", cmd_read)
    p.add_argument("--chapter", required=True)
    p.add_argument("--pages")
    p.add_argument("--max-tokens", type=int, default=4000)
    p = add("validate", cmd_validate)
    p.add_argument("--stage", choices=["outline", "lesson", "course"], default="course")
    p.add_argument("--lesson")
    p = add("render", cmd_render)
    p.add_argument("--partial", action="store_true", help="render only lessons that have drafts")
    p.add_argument("--skip-validate", action="store_true")
    add("status", cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
