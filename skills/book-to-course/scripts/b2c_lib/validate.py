"""Stage 7 — deterministic self-check: schema, coverage, page citations, quote fidelity, quiz sanity.

Everything an LLM could get wrong *structurally* is checked here, identically for every model.
Errors fail the run (exit 1); warnings are advisory. Results go to work/report.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import Work, norm_for_match, read_json, write_json
from .diagrams import check_diagram
from .mathtex import check_latex, grounding, latex_atoms, split_math, unescaped_dollars
from .paras import page_code, page_text

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
MAX_QUOTE_WORDS = 25
MAX_TASK_WORDS = 120
MAX_CODE_LINES = 30
SHOWN_SIMILARITY = 0.85  # a book problem statement copied verbatim as a practice task (not counted as a quote)
MAX_QUOTES_SHARE = 0.15
TERM_RE = re.compile(r"\[\[(.+?)\]\]")
WEAK_VERBS = re.compile(r"^(understand|know|learn|be aware|become familiar|get|понять|знать|изучить|ознакомиться)\b", re.I)
MEMORY_Q = re.compile(r"^(what does .+ stand for|which (file|chapter|page)|what (year|page)|что означает аббревиатура|на какой странице)", re.I)

# ── mini JSON-schema ─────────────────────────────────────────────────────

_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}


def check_schema(data, schema: dict, path: str = "$") -> list[str]:
    errs: list[str] = []
    t = schema.get("type")
    if t:
        ok = isinstance(data, _TYPES[t]) and not (t in ("integer", "number") and isinstance(data, bool))
        if not ok:
            return [f"{path}: expected {t}, got {type(data).__name__}"]
    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}: {data!r} not in {schema['enum']}")
    if isinstance(data, str):
        if len(data) < schema.get("minLength", 0):
            errs.append(f"{path}: string shorter than {schema['minLength']}")
        if len(data) > schema.get("maxLength", 10**9):
            errs.append(f"{path}: string longer than {schema['maxLength']} chars ({len(data)})")
        if "pattern" in schema and not re.search(schema["pattern"], data):
            errs.append(f"{path}: {data!r} does not match {schema['pattern']}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errs.append(f"{path}: {data} < minimum {schema['minimum']}")
    if isinstance(data, list):
        if len(data) < schema.get("minItems", 0):
            errs.append(f"{path}: needs >= {schema['minItems']} items, has {len(data)}")
        if len(data) > schema.get("maxItems", 10**9):
            errs.append(f"{path}: allows <= {schema['maxItems']} items, has {len(data)}")
        if "items" in schema:
            for i, it in enumerate(data):
                errs += check_schema(it, schema["items"], f"{path}[{i}]")
    if isinstance(data, dict):
        for r in schema.get("required", []):
            if r not in data:
                errs.append(f"{path}: missing required field '{r}'")
        for k, sub in schema.get("properties", {}).items():
            if k in data:
                errs += check_schema(data[k], sub, f"{path}.{k}")
        by = schema.get("x-by-type")
        if by:
            typ = data.get(by["field"])
            spec = by["schemas"].get(typ)
            if spec is None:
                errs.append(f"{path}: unknown {by['field']} {typ!r}; allowed {sorted(by['schemas'])}")
            else:
                for r in spec["required"]:
                    if r not in data:
                        errs.append(f"{path}({typ}): missing '{r}'")
                for k, kind in spec["props"].items():
                    if k in data:
                        errs += _check_kind(data[k], kind, f"{path}({typ}).{k}")
    return errs


def _check_kind(v, kind: str, path: str) -> list[str]:
    if kind == "string":
        return [] if isinstance(v, str) and v.strip() else [f"{path}: must be a non-empty string"]
    if kind == "page":
        return [] if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else [f"{path}: must be a page integer >= 1"]
    if kind == "pages":
        ok = isinstance(v, list) and all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in v)
        return [] if ok else [f"{path}: must be a list of page integers"]
    if kind == "variant":
        return [] if v in ("accent", "info", "warning") else [f"{path}: must be accent|info|warning"]
    if kind == "origin":
        return [] if v in ("book", "derived") else [f"{path}: must be 'book' (formula is in the source) or 'derived' (you derived it)"]
    if kind == "checked":
        return [] if v == "image" else [f"{path}: must be 'image' (you compared the formula with the page image) or omitted"]
    if kind == "codelines":
        ok = isinstance(v, list) and 1 <= len(v) <= 14 and all(
            isinstance(x, dict) and str(x.get("at", "")).strip() and str(x.get("text", "")).strip() for x in v)
        return [] if ok else [f"{path}: needs 1-14 items, each with `at` ('3' or '3-5') and `text` (plain words)"]
    if kind == "symbols":
        ok = isinstance(v, list) and 1 <= len(v) <= 10 and all(
            isinstance(x, dict) and str(x.get("sym", "")).strip() and str(x.get("meaning", "")).strip() for x in v)
        return [] if ok else [f"{path}: needs 1-10 items, each with non-empty sym (LaTeX) and meaning (plain words)"]
    if kind == "titled-items":
        if not isinstance(v, list) or not 2 <= len(v) <= 6:
            return [f"{path}: needs 2-6 items"]
        bad = [i for i, it in enumerate(v) if not (isinstance(it, dict) and str(it.get("title", "")).strip() and str(it.get("text", "")).strip())]
        return [f"{path}[{i}]: needs non-empty title and text" for i in bad]
    return []


def load_schema(name: str) -> dict:
    return json.loads((TEMPLATES / name).read_text(encoding="utf-8"))


# ── helpers ──────────────────────────────────────────────────────────────


class Result:
    def __init__(self, scope: str):
        self.scope, self.errors, self.warnings = scope, [], []

    def err(self, m: str) -> None:
        self.errors.append(m)

    def warn(self, m: str) -> None:
        self.warnings.append(m)

    def as_dict(self) -> dict:
        return {"scope": self.scope, "errors": self.errors, "warnings": self.warnings}


def _lessons(outline: dict):
    for m in outline.get("modules", []):
        for l in m.get("lessons", []):
            yield m, l


def _chapter_map(manifest: dict) -> dict:
    return {c["id"]: c for c in manifest["chapters"]}


def _words(t: str) -> list[str]:
    return re.findall(r"[^\W\d_]{3,}", norm_for_match(t))


def _words_match(words: list[str], hay: list[str]) -> float:
    """Share of `words` found in order in `hay` (text-layer garbage around math does not matter: only 3+ letter words count)."""
    from difflib import SequenceMatcher

    if not words:
        return 1.0
    sm = SequenceMatcher(None, words, hay, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(words)


def _page_words(work: Work, page: int) -> list[str]:
    return _words(page_text(work, page) + " " + page_text(work, page + 1))


def _read_full_pages(les: dict) -> set[int]:
    out: set[int] = set()
    for rf in les["sources"].get("read_full", []):
        m = re.fullmatch(r"\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*", str(rf.get("pages", "")))
        if m:
            a = int(m.group(1))
            out.update(range(a, int(m.group(2) or a) + 1))
    return out


def _allowed_pages(lesson: dict, chap: dict) -> set[int]:
    pages: set[int] = set()
    for ref in lesson["source_refs"]:
        c = chap.get(ref["chapter"])
        if not c:
            continue
        a, b = ref.get("pages") or [c["page_start"], c["page_end"]]
        pages.update(range(a, b + 1))
    return pages


# ── outline ──────────────────────────────────────────────────────────────


def validate_outline(work: Work) -> Result:
    r = Result("outline")
    if not work.outline.exists():
        r.err(f"{work.outline} does not exist")
        return r
    outline = read_json(work.outline)
    r.errors += check_schema(outline, load_schema("outline.schema.json"))
    if r.errors:
        return r
    manifest = read_json(work.manifest)
    chap = _chapter_map(manifest)
    mids, lids = set(), set()
    covered: set[str] = set()
    for m in outline["modules"]:
        if m["id"] in mids:
            r.err(f"duplicate module id {m['id']}")
        mids.add(m["id"])
        if not 2 <= len(m["lessons"]) <= 6:
            r.warn(f"{m['id']}: {len(m['lessons'])} lessons (2-6 is the sweet spot)")
    for m, l in _lessons(outline):
        if l["id"] in lids:
            r.err(f"duplicate lesson id {l['id']}")
        lids.add(l["id"])
        for o in l["objectives"]:
            if WEAK_VERBS.match(o.strip()):
                r.warn(f"{l['id']}: objective starts with a weak verb: {o[:50]!r} (use explain/derive/compare/apply...)")
        if len({ref['chapter'] for ref in l["source_refs"]}) > 3:
            r.warn(f"{l['id']}: cites >3 chapters; consider splitting")
        for ref in l["source_refs"]:
            c = chap.get(ref["chapter"])
            if not c:
                r.err(f"{l['id']}: source_ref chapter {ref['chapter']} is not in the manifest (scope/ids?)")
                continue
            covered.add(ref["chapter"])
            if "pages" in ref:
                a, b = ref["pages"]
                if a > b or a < c["page_start"] or b > c["page_end"]:
                    r.err(f"{l['id']}: pages {a}-{b} outside {c['id']} range {c['page_start']}-{c['page_end']}")
    skipped = {s["chapter"] for s in outline.get("skipped", [])}
    for cid in skipped:
        if cid not in chap:
            r.err(f"skipped chapter {cid} not in manifest")
    for c in manifest["chapters"]:
        if c["kind"] == "chapter" and c["id"] not in covered and c["id"] not in skipped:
            r.err(f"coverage: {c['id']} '{c['title']}' (pp.{c['page_start']}-{c['page_end']}) is in no lesson; "
                  f"add it to a lesson's source_refs or to `skipped` with a reason")
    return r


# ── lesson ───────────────────────────────────────────────────────────────


def _lesson_texts(les: dict):
    for s in les["screens"]:
        for b in s["blocks"]:
            t = b["type"]
            if t == "text":
                yield b["text"]
            elif t in ("cards", "steps"):
                for it in b["items"]:
                    yield it["title"]
                    yield it["text"]
            elif t == "callout":
                yield b["title"]
                yield b["text"]
            elif t == "quote":
                yield b["meaning"]
            elif t == "code":
                for ln in b["lines"]:
                    yield ln["text"]
                if b.get("note"):
                    yield b["note"]
            elif t == "task":
                yield b["plain"]
                if b.get("hint"):
                    yield b["hint"]
            elif t == "math":
                for sy in b["symbols"]:
                    yield sy["meaning"]
                if b.get("caption"):
                    yield b["caption"]


def _shingles(text: str, n: int) -> set[tuple]:
    w = norm_for_match(text).split()
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def validate_lesson(work: Work, lesson_id: str) -> Result:
    r = Result(lesson_id)
    f = work.drafts / f"{lesson_id}.json"
    if not f.exists():
        r.err(f"draft {f} missing")
        return r
    try:
        les = read_json(f)
    except json.JSONDecodeError as e:
        r.err(f"invalid JSON: {e}")
        return r
    r.errors += check_schema(les, load_schema("lesson.schema.json"))
    if r.errors:
        return r
    outline, manifest = read_json(work.outline), read_json(work.manifest)
    chap = _chapter_map(manifest)
    found = [(m, l) for m, l in _lessons(outline) if l["id"] == lesson_id]
    if not found:
        r.err("lesson id not in outline")
        return r
    _m, spec = found[0]
    allowed = _allowed_pages(spec, chap) | _read_full_pages(les)   # pages named in source_refs + pages the model read in full
    loose: set[int] = set()                                       # any page of the chapters the lesson cites
    for ref in spec["source_refs"]:
        c = chap.get(ref["chapter"])
        if c:
            loose.update(range(c["page_start"], c["page_end"] + 1))
    warned_pages: set[int] = set()
    n_obj = len(spec["objectives"])

    # objectives
    covered = {i for s in les["screens"] for i in s["covers"]}
    for i in covered:
        if i >= n_obj:
            r.err(f"screens[].covers index {i} out of range (lesson has {n_obj} objectives)")
    for i in range(n_obj):
        if i not in covered:
            r.err(f"objective {i} ('{spec['objectives'][i][:50]}') is covered by no screen")

    # sources
    refs = {x["chapter"] for x in spec["source_refs"]}
    if set(les["sources"]["chapters"]) != refs:
        r.err(f"sources.chapters {sorted(les['sources']['chapters'])} != outline source_refs {sorted(refs)}")

    # citations
    def check_pages(pages, where):
        for p in pages:
            if p not in allowed and p not in loose:
                r.err(f"{where}: cites p.{p}, outside the chapters this lesson cites")
            elif not page_text(work, p) and not page_code(work, p):
                r.err(f"{where}: p.{p} has no extracted text")
            elif p not in allowed and p not in warned_pages:
                warned_pages.add(p)
                r.warn(f"{where}: p.{p} is inside the cited chapter but outside this lesson's source_refs pages; "
                       f"widen source_refs.pages in outline.json, or list the pages in sources.read_full")

    quote_words = lesson_words = 0
    all_cited: set[int] = set()
    for s in les["screens"]:
        cites, visual = [], False
        for bi, b in enumerate(s["blocks"]):
            where = f"screen {s['id']} block {bi} ({b['type']})"
            if b["type"] == "quote":
                cites.append(b["page"])
                visual = True
                check_pages([b["page"]], where)
                nw = len(b["text"].split())
                quote_words += nw
                if nw > MAX_QUOTE_WORDS:
                    r.err(f"{where}: quote is {nw} words (max {MAX_QUOTE_WORDS}); shorten and paraphrase the rest")
                elif nw < 3:
                    r.err(f"{where}: quote shorter than 3 words")
                _check_quote(work, b["text"], b["page"], where, r)
                if b.get("shown"):
                    _check_shown(b["shown"], b["text"], where, r)
            elif b["type"] == "code":
                cites.append(b["page"])
                visual = True
                check_pages([b["page"]], where)
                _check_code(work, b, where, r)
            elif b["type"] == "figure":
                cites.append(b["page"])
                visual = True
                check_pages([b["page"]], where)
                _check_figure(work, b, where, r)
            elif b["type"] == "task":
                cites.append(b["page"])
                visual = True
                check_pages([b["page"]], where)
                nw = len(b["statement"].split())
                if nw > MAX_TASK_WORDS:
                    r.err(f"{where}: task statement is {nw} words (max {MAX_TASK_WORDS}); copy only the problem itself")
                elif nw < 4:
                    r.err(f"{where}: task statement shorter than 4 words")
                sw = _words(b["statement"])
                if len(sw) < 3:
                    r.err(f"{where}: statement has fewer than 3 words of 3+ letters; copy the problem text, put the math in `shown`")
                else:
                    ratio = _words_match(sw, _page_words(work, b["page"]))
                    if ratio < 0.9:
                        r.err(f"{where}: statement matches the page text only {ratio:.0%} (need 90%); copy the problem as it is printed, "
                              f"garbled math symbols are fine, and put the clean version in `shown`")
                if b.get("shown"):
                    _check_shown(b["shown"], b["statement"], where, r)
                if len(b["plain"].split()) < 6:
                    r.err(f"{where}: `plain` must restate in your own words what the task asks (at least 6 words)")
            else:
                cites += b["cite"]
                check_pages(b["cite"], where)
                if b["type"] == "math":
                    _check_math_block(work, b, where, r)
                if b["type"] == "diagram":
                    for e in check_diagram(b):
                        r.err(f"{where}: {e}")
                if b["type"] != "text":
                    visual = True
                else:
                    if len(b["text"].split()) > 90:
                        r.err(f"{where}: text block is {len(b['text'].split())} words (max 90): split it or use cards/steps")
        if not cites:
            r.err(f"screen {s['id']}: no page citation anywhere on the screen")
        if not visual:
            r.err(f"screen {s['id']}: only plain text blocks; add cards/steps/quote/callout (rubric: visual first)")
        all_cited.update(cites)
    for t in _lesson_texts(les):
        lesson_words += len(re.sub(r"\[\[|\]\]", "", t).split())
    if lesson_words and quote_words / (lesson_words + quote_words) > MAX_QUOTES_SHARE:
        r.err(f"quotes are {quote_words / (lesson_words + quote_words):.0%} of the lesson (max {MAX_QUOTES_SHARE:.0%}): paraphrase more")
    if not any(b["type"] in ("quote", "code") for s in les["screens"] for b in s["blocks"]):
        r.warn("no quote block (source <-> plain-language translation); the course needs at least one per module")
    if not any(b["type"] in ("figure", "diagram") for s in les["screens"] for b in s["blocks"]):
        r.warn("no figure or diagram in this lesson; add one where the idea is spatial, a process, or a function (rubric: visual)")
    if sum(1 for s in les["screens"] for b in s["blocks"] if b["type"] == "callout") > 2:
        r.warn("more than 2 callouts in one lesson")

    # long verbatim copying outside quote blocks
    src = " ".join(page_text(work, p) for p in sorted(allowed))
    sh = _shingles(src, 12)
    for t in _lesson_texts(les):
        w = norm_for_match(re.sub(r"\[\[|\]\]", "", t)).split()
        run = best = 0
        for i in range(len(w) - 11):
            if tuple(w[i:i + 12]) in sh:
                run += 1
                best = max(best, run)
            else:
                run = 0
        if best:
            n = best + 11
            (r.err if n >= 25 else r.warn)(f"{n}-word run copied from the source outside a quote block: {t[:60]!r}...")

    # inline math ($...$) anywhere in the lesson text
    for where, t in _all_strings(les):
        if "$$" in t:
            r.err(f"{where}: '$$' is not allowed in running text; use a math block for display formulas")
            continue
        if unescaped_dollars(t) % 2:
            r.err(f"{where}: unbalanced $ (write a literal dollar as \\$): {t[:50]!r}")
            continue
        for kind, seg in split_math(t):
            if kind == "math":
                for e in check_latex(seg, display=False):
                    r.err(f"{where}: inline math ${seg[:40]}$: {e}")
    for g in les["glossary"]:
        if "$" in g["definition"] or "$" in g["term"]:
            r.err(f"glossary '{g['term']}': tooltips are plain text; describe the formula in words")

    # quiz
    for i, q in enumerate(les["quiz"]):
        if q["answer"] >= len(q["options"]):
            r.err(f"quiz[{i}]: answer index {q['answer']} out of range")
        if len({o.strip().lower() for o in q["options"]}) != len(q["options"]):
            r.err(f"quiz[{i}]: duplicate options")
        if MEMORY_Q.match(q["question"].strip()):
            r.warn(f"quiz[{i}]: tests recall, not application: {q['question'][:50]!r}")
        check_pages(q["cite"], f"quiz[{i}]")
    if len(les["quiz"]) >= 3 and len({q["answer"] for q in les["quiz"]}) == 1:
        r.warn("every quiz answer has the same position; vary it")

    # glossary
    gl = {g["term"].strip().lower(): g for g in les["glossary"]}
    for g in les["glossary"]:
        check_pages(g["cite"], f"glossary '{g['term']}'")
    used = set()
    for t in _lesson_texts(les):
        for m in TERM_RE.findall(t):
            k = m.strip().lower()
            used.add(k)
            if k not in gl:
                r.err(f"[[{m}]] is marked as a term but has no glossary entry")
    for k in gl:
        if k not in used:
            r.warn(f"glossary term '{k}' is never marked with [[...]] in the text")
    if len(used) < 3:
        r.warn(f"only {len(used)} glossary terms marked; rubric asks for every non-obvious term")
    return r


def _check_shown(shown: str, source: str, where: str, r: Result) -> None:
    """`shown` is the clean version displayed to the learner (may contain $math$); it must say the same thing as the verbatim source."""
    plain = "".join(seg for kind, seg in split_math(shown) if kind == "text")
    ws, wsrc = _words(plain), _words(source)
    if ws and _words_match(ws, wsrc) < SHOWN_SIMILARITY:
        r.err(f"{where}: `shown` differs from the verbatim source (words match {_words_match(ws, wsrc):.0%}, need {SHOWN_SIMILARITY:.0%}); "
              f"only fix formatting and math, do not reword")


def _check_code(work: Work, b: dict, where: str, r: Result) -> None:
    code = b["code"].strip("\n")
    n = len(code.split("\n"))
    if n > MAX_CODE_LINES:
        r.err(f"{where}: code is {n} lines (max {MAX_CODE_LINES}); show the part the lesson explains")
    hay = re.sub(r"\s+", "", "".join(page_code(work, p) for p in (b["page"], b["page"] + 1)) + page_text(work, b["page"]))
    parts = [p for p in re.split(r"(?m)^\s*(?:\.\.\.|…|#\s*(?:\.\.\.|…))\s*$", code) if p.strip()]
    pos = 0
    for part in parts:
        needle = re.sub(r"\s+", "", part)
        k = hay.find(needle, pos)
        if k < 0:
            r.err(f"{where}: code is not found verbatim on p.{b['page']} (whitespace ignored): {part.strip()[:50]!r}")
            return
        pos = k + len(needle)
    for ln in b["lines"]:
        m = re.fullmatch(r"\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*", str(ln["at"]))
        if not m or not 1 <= int(m.group(1)) <= (int(m.group(2)) if m.group(2) else int(m.group(1))) <= n:
            r.err(f"{where}: lines[].at {ln['at']!r} must be 'N' or 'N-M' within 1..{n}")
        if len(str(ln["text"]).split()) < 4:
            r.err(f"{where}: each lines[].text explains in plain words (at least 4 words)")


def _all_strings(les: dict):
    """Every learner-visible string that may carry inline math, with a location label."""
    for k in ("metaphor", "hook", "why_care"):
        yield k, les[k]
    for i, t in enumerate(les["key_takeaways"]):
        yield f"key_takeaways[{i}]", t
    for s in les["screens"]:
        yield f"screen {s['id']} heading", s["heading"]
        for bi, b in enumerate(s["blocks"]):
            w = f"screen {s['id']} block {bi}"
            t = b["type"]
            if t == "text":
                yield w, b["text"]
            elif t in ("cards", "steps"):
                for it in b["items"]:
                    yield w, it["title"]
                    yield w, it["text"]
            elif t == "callout":
                yield w, b["title"]
                yield w, b["text"]
            elif t == "quote":
                yield w, b["meaning"]
                if b.get("shown"):
                    yield w + " shown", b["shown"]
            elif t == "code":
                for ln in b["lines"]:
                    yield w + " explanation", ln["text"]
                if b.get("note"):
                    yield w + " note", b["note"]
            elif t == "task":
                if b.get("shown"):
                    yield w + " shown", b["shown"]
                yield w + " plain", b["plain"]
                if b.get("hint"):
                    yield w + " hint", b["hint"]
            elif t == "math":
                for sy in b["symbols"]:
                    yield w + " meaning", sy["meaning"]
                if b.get("caption"):
                    yield w + " caption", b["caption"]
    for i, q in enumerate(les["quiz"]):
        yield f"quiz[{i}] question", q["question"]
        for o in q["options"]:
            yield f"quiz[{i}] option", o
        yield f"quiz[{i}] explain_right", q["explain_right"]
        yield f"quiz[{i}] explain_wrong", q["explain_wrong"]


def _check_figure(work: Work, b: dict, where: str, r: Result) -> None:
    from pathlib import Path

    from .figtools import crop_fig, find_fig

    try:
        fig = find_fig(work, b["fig"])
    except Exception as ex:  # noqa: BLE001
        r.err(f"{where}: {ex}")
        return
    if fig["page"] != b["page"]:
        r.err(f"{where}: {b['fig']} is on p.{fig['page']}, not p.{b['page']}")
    if len(b["caption"].split()) < 5:
        r.err(f"{where}: caption must say in your own words what the figure shows (at least 5 words)")
    pdf = Path(read_json(work.manifest)["book"]["pdf"])
    if not crop_fig(pdf, fig, work.root / "fig" / f"{b['fig']}.png"):
        r.err(f"{where}: {b['fig']} has no separable graphics to crop (scanned or embedded in the page); "
              f"describe it with a `diagram` instead, or look at `b2c.py page-image`")


def _check_math_block(work: Work, b: dict, where: str, r: Result) -> None:
    from .eqtools import find_eq

    for e in check_latex(b["latex"], display=True):
        r.err(f"{where}: {e}")
    if not b["cite"]:
        r.err(f"{where}: math block needs a cite (the page(s) it comes from or is derived from)")
        return
    if b["origin"] == "derived":
        if not b.get("caption"):
            r.warn(f"{where}: derived formula without a caption saying how it follows from the source")
    else:
        text = " ".join(page_text(work, p) for p in b["cite"])
        score, miss = grounding(b["latex"], text)
        if score is None:
            if not b.get("eq"):
                r.warn(f"{where}: formula has no distinctive symbols to verify against the page; add `eq` (id) or check the page image")
        elif score < 0.5 and b.get("checked_against") == "image":
            r.warn(f"{where}: formula symbols {sorted(miss)} are not in the text layer of p.{b['cite']}; accepted because you "
                   f"checked it against the page image (checked_against: image)")
        elif score < 0.5:
            r.err(f"{where}: formula symbols {sorted(miss)} do not appear on cited p.{b['cite']}: copy it from the source "
                  f"(see `b2c.py eq`), or look at the page image and set checked_against: \"image\"; set origin 'derived' only if you derived it")
        elif score < 0.8:
            r.warn(f"{where}: only {score:.0%} of the formula's distinctive symbols appear on the cited pages ({sorted(miss)})")
    if b.get("eq"):
        try:
            eq = find_eq(work, b["eq"])
        except Exception as ex:  # noqa: BLE001
            r.err(f"{where}: eq id {b['eq']!r}: {ex}")
        else:
            if eq["page"] not in b["cite"]:
                r.err(f"{where}: eq {b['eq']} is on p.{eq['page']}, which is not in cite {b['cite']}")
            if b["origin"] == "book":
                score, miss = grounding(b["latex"], eq["text"])
                if score is not None and score < 0.5 and b.get("checked_against") != "image":
                    r.err(f"{where}: latex does not match {b['eq']} (source text: {eq['text'][:60]!r}; missing {sorted(miss)})")
    greek = set(re.findall(r"\\(alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|Omega)(?![A-Za-z])", b["latex"]))
    sym_text = " ".join(sy["sym"] for sy in b["symbols"])
    for gname in sorted(greek):
        if "\\" + gname not in sym_text:
            r.warn(f"{where}: \\{gname} appears in the formula but is not in `symbols`; name every symbol once")


def _check_quote(work: Work, text: str, page: int, where: str, r: Result) -> None:
    hay = norm_for_match(page_text(work, page) + " " + page_text(work, page + 1))
    parts = [p for p in re.split(r"…|\[\.\.\.\]|\.\.\.", text) if len(p.split()) >= 2]
    pos = 0
    for part in parts or [text]:
        needle = norm_for_match(part)
        k = hay.find(needle, pos)
        if k < 0:
            r.err(f"{where}: quote not found verbatim on p.{page}: {part[:60]!r}")
            return
        pos = k + len(needle)


# ── whole course ─────────────────────────────────────────────────────────


def validate_course(work: Work) -> list[Result]:
    results = [validate_outline(work)]
    if results[0].errors:
        return results
    outline = read_json(work.outline)
    metaphors: dict[str, str] = {}
    for m, l in _lessons(outline):
        lr = validate_lesson(work, l["id"])
        results.append(lr)
        f = work.drafts / f"{l['id']}.json"
        if f.exists() and not lr.errors:
            les = read_json(f)
            key = " ".join(re.findall(r"\w+", les["metaphor"].lower())[:4])
            if les["metaphor"] and re.search(r"restaurant|kitchen|ресторан|кухн", les["metaphor"], re.I):
                lr.warn("metaphor is restaurant/kitchen (overused)")
            if key in metaphors:
                lr.warn(f"metaphor starts like {metaphors[key]}'s; use a fresh one per lesson")
            metaphors.setdefault(key, l["id"])
    course = Result("course")
    for m in outline["modules"]:
        has_quote = False
        for l in m["lessons"]:
            f = work.drafts / f"{l['id']}.json"
            if f.exists():
                try:
                    has_quote |= any(b["type"] in ("quote", "code") for s in read_json(f)["screens"] for b in s["blocks"])
                except Exception:
                    pass
        if not has_quote:
            course.err(f"{m['id']}: no quote block in any lesson (source <-> plain-language translation is required per module)")
    results.append(course)
    return results


def usage_summary(work: Work) -> dict:
    out = {"select_tokens": 0, "full_read_tokens": 0, "full_reads": 0}
    if work.usage.exists():
        for line in work.usage.read_text().splitlines():
            u = json.loads(line)
            if u["kind"] == "select":
                out["select_tokens"] += u["tokens"]
            elif u["kind"] == "full_read":
                out["full_read_tokens"] += u["tokens"]
                out["full_reads"] += 1
    return out


def write_report(work: Work, results: list[Result]) -> dict:
    manifest = read_json(work.manifest) if work.manifest.exists() else {}
    rep = {"ok": all(not r.errors for r in results),
           "results": [r.as_dict() for r in results],
           "usage": usage_summary(work),
           "book_tokens_estimate": manifest.get("totals", {}).get("est_tokens")}
    write_json(work.report, rep)
    return rep
