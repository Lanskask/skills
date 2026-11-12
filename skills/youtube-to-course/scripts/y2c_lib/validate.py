"""Stage 7 — deterministic self-check: schema, segment coverage, timestamp validity, quote fidelity, quiz sanity.

Everything an LLM could get wrong *structurally* is checked here, identically for every model.
Errors fail the run (exit 1); warnings are advisory. Results go to work/report.json.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .common import Work, fmt_time, norm_for_match, parse_time, read_json, write_json
from .diagrams import check_diagram
from .mathtex import check_latex, split_math, unescaped_dollars

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
MAX_QUOTE_WORDS = 25
MAX_QUOTES_SHARE = 0.15
SLACK = 10          # seconds a citation may lie outside its segment (caption timing is only ~±5 s accurate)
QUOTE_WINDOW = (30, 45)   # a quote must be found within [at-30 s, at+45 s]
QUOTE_MATCH = 0.9
TERM_RE = re.compile(r"\[\[(.+?)\]\]")
WEAK_VERBS = re.compile(r"^(understand|know|learn|be aware|become familiar|get|понять|знать|изучить|ознакомиться)\b", re.I)
MEMORY_Q = re.compile(r"^(what does .+ stand for|which (file|chapter|minute|video)|what (year|minute)|что означает аббревиатура|на какой минуте)", re.I)

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


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _check_kind(v, kind: str, path: str) -> list[str]:
    if kind == "string":
        return [] if isinstance(v, str) and v.strip() else [f"{path}: must be a non-empty string"]
    if kind == "time":
        return [] if _is_int(v) and v >= 0 else [f"{path}: must be whole seconds >= 0 (the number after | in the pack's [m:ss|sec] markers)"]
    if kind == "times":
        ok = isinstance(v, list) and len(v) >= 1 and all(_is_int(x) and x >= 0 for x in v)
        return [] if ok else [f"{path}: must be a non-empty list of whole seconds (from the pack's [m:ss|sec] markers)"]
    if kind == "variant":
        return [] if v in ("accent", "info", "warning") else [f"{path}: must be accent|info|warning"]
    if kind == "origin":
        return [] if v in ("video", "derived") else [f"{path}: must be 'video' (the formula is shown or said in the video) or 'derived' (you derived it)"]
    if kind == "checked":
        return [] if v == "screen" else [f"{path}: must be 'screen' (you checked it against on-screen text in the pack) or omitted"]
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
        for lsn in m.get("lessons", []):
            yield m, lsn


def _words(t: str) -> list[str]:
    return re.findall(r"[^\W\d_]{2,}", norm_for_match(t))


def _words_match(words: list[str], hay: list[str]) -> float:
    """Share of `words` found in order in `hay`."""
    if not words:
        return 1.0
    sm = SequenceMatcher(None, words, hay, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(words)


def _cue_lines(work: Work, vid: str) -> list[dict]:
    p = work.vdir(vid) / "cues.json"
    return read_json(p)["lines"] if p.exists() else []


def _window_text(work: Work, vid: str, a: float, b: float) -> str:
    return " ".join(ln["text"] for ln in _cue_lines(work, vid) if ln["end"] >= a and ln["start"] <= b)


def _range(spec: str) -> tuple[int, int]:
    a, _, b = str(spec).replace("–", "-").partition("-")
    return parse_time(a), parse_time(b or a)


def _lesson_video(spec: dict, seg: dict) -> set[str]:
    return {seg[r["segment"]]["video"] for r in spec["source_refs"] if r["segment"] in seg}


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
    seg = {s["id"]: s for s in manifest["segments"]}
    vids = {v["id"] for v in manifest["videos"]}
    mids, lids = set(), set()
    covered: set[str] = set()
    for m in outline["modules"]:
        if m["id"] in mids:
            r.err(f"duplicate module id {m['id']}")
        mids.add(m["id"])
        if m["video"] not in vids:
            r.err(f"{m['id']}: video {m['video']} is not in the manifest ({sorted(vids)})")
        if not 2 <= len(m["lessons"]) <= 6:
            r.warn(f"{m['id']}: {len(m['lessons'])} lessons (2-6 is the sweet spot)")
    for m, lsn in _lessons(outline):
        if lsn["id"] in lids:
            r.err(f"duplicate lesson id {lsn['id']}")
        lids.add(lsn["id"])
        for o in lsn["objectives"]:
            if WEAK_VERBS.match(o.strip()):
                r.warn(f"{lsn['id']}: objective starts with a weak verb: {o[:50]!r} (use explain/derive/compare/apply...)")
        for ref in lsn["source_refs"]:
            s = seg.get(ref["segment"])
            if not s:
                r.err(f"{lsn['id']}: segment {ref['segment']} is not in the manifest")
                continue
            covered.add(ref["segment"])
            if s["video"] != m["video"]:
                r.err(f"{lsn['id']}: segment {ref['segment']} belongs to {s['video']} but module {m['id']} is {m['video']} (one video per module)")
    skipped = {s["segment"] for s in outline.get("skipped", [])}
    for sid in skipped:
        if sid not in seg:
            r.err(f"skipped segment {sid} not in manifest")
    for s in manifest["segments"]:
        if s["kind"] == "content" and s["id"] not in covered and s["id"] not in skipped:
            r.err(f"coverage: {s['id']} '{s['title']}' ({fmt_time(s['start'])}-{fmt_time(s['end'])}, {s['video']}) is in no lesson; "
                  f"add it to a lesson's source_refs or to `skipped` with a reason")
    for v in vids:
        if not any(m["video"] == v for m in outline["modules"]):
            r.err(f"video {v} has no module")
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
            elif t == "math":
                for sy in b["symbols"]:
                    yield sy["meaning"]
                if b.get("caption"):
                    yield b["caption"]


def _all_strings(les: dict):
    for k in ("metaphor", "hook", "why_care"):
        yield k, les[k]
    for s in les["screens"]:
        yield f"screen {s['id']} heading", s["heading"]
        for bi, b in enumerate(s["blocks"]):
            w = f"screen {s['id']} block {bi} ({b['type']})"
            for t in _lesson_texts({"screens": [{"blocks": [b]}]}):
                yield w, t
            if b["type"] == "diagram":
                continue
    for i, q in enumerate(les["quiz"]):
        yield f"quiz[{i}].question", q["question"]
        for o in q["options"]:
            yield f"quiz[{i}].option", o
        yield f"quiz[{i}].explain_right", q["explain_right"]
        yield f"quiz[{i}].explain_wrong", q["explain_wrong"]
    for t in les["key_takeaways"]:
        yield "key_takeaways", t


def _wordlist(text: str) -> list[str]:
    return re.findall(r"\w+", norm_for_match(text))


def _shingles(text: str, n: int) -> set[tuple]:
    w = _wordlist(text)
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
    seg = {s["id"]: s for s in manifest["segments"]}
    vmeta = {v["id"]: v for v in manifest["videos"]}
    found = [(m, lsn) for m, lsn in _lessons(outline) if lsn["id"] == lesson_id]
    if not found:
        r.err("lesson id not in outline")
        return r
    mod, spec = found[0]
    vid = mod["video"]
    duration = vmeta[vid]["duration"]
    my = [seg[x["segment"]] for x in spec["source_refs"] if x["segment"] in seg]
    windows = [(s["start"] - SLACK, s["end"] + SLACK) for s in my]
    for rf in les["sources"].get("read_full", []):
        try:
            a, b = _range(rf["range"])
            windows.append((a - SLACK, b + SLACK))
        except ValueError:
            r.err(f"sources.read_full range {rf['range']!r} is not like '90-240' or '1:30-4:00'")
    same_video = [(s["start"] - SLACK, s["end"] + SLACK) for s in manifest["segments"] if s["video"] == vid]
    warned: set[int] = set()
    n_obj = len(spec["objectives"])

    covered = {i for s in les["screens"] for i in s["covers"]}
    for i in covered:
        if i >= n_obj:
            r.err(f"screens[].covers index {i} out of range (lesson has {n_obj} objectives)")
    for i in range(n_obj):
        if i not in covered:
            r.err(f"objective {i} ('{spec['objectives'][i][:50]}') is covered by no screen")

    refs = {x["segment"] for x in spec["source_refs"]}
    if set(les["sources"]["segments"]) != refs:
        r.err(f"sources.segments {sorted(les['sources']['segments'])} != outline source_refs {sorted(refs)}")

    def check_times(times, where):
        for t in times:
            if t > duration:
                r.err(f"{where}: timestamp {t}s is beyond the video ({duration}s)")
            elif any(a <= t <= b for a, b in windows):
                continue
            elif any(a <= t <= b for a, b in same_video):
                if t not in warned:
                    warned.add(t)
                    r.warn(f"{where}: {t}s ({fmt_time(t)}) is in another segment of the same video; add that segment to source_refs or `read_full`")
            else:
                r.err(f"{where}: {t}s ({fmt_time(t)}) is outside every segment of {vid} (no speech there, or another video)")

    quote_words = lesson_words = 0
    for s in les["screens"]:
        cites, visual = [], False
        for bi, b in enumerate(s["blocks"]):
            where = f"screen {s['id']} block {bi} ({b['type']})"
            if b["type"] == "quote":
                cites.append(b["at"])
                visual = True
                check_times([b["at"]], where)
                nw = len(b["text"].split())
                quote_words += nw
                if nw > MAX_QUOTE_WORDS:
                    r.err(f"{where}: quote is {nw} words (max {MAX_QUOTE_WORDS}); shorten and paraphrase the rest")
                elif nw < 3:
                    r.err(f"{where}: quote shorter than 3 words")
                qw = _words(b["text"])
                hay = _words(_window_text(work, vid, b["at"] - QUOTE_WINDOW[0], b["at"] + QUOTE_WINDOW[1]))
                ratio = _words_match(qw, hay)
                if ratio < QUOTE_MATCH:
                    r.err(f"{where}: quote matches the transcript near {fmt_time(b['at'])} only {ratio:.0%} (need {QUOTE_MATCH:.0%}); "
                          f"copy it as printed in the pack, or fix `at`")
            else:
                cites += b["cite"]
                check_times(b["cite"], where)
                if b["type"] == "math":
                    for e in check_latex(b["latex"], display=True):
                        r.err(f"{where}: {e}")
                    if b["origin"] == "derived" and not b.get("caption"):
                        r.err(f"{where}: a `derived` formula needs a caption saying what it is derived from")
                    if b["origin"] == "video" and b.get("checked_against") != "screen":
                        r.warn(f"{where}: formula from the video is not checked against on-screen text (audio rarely carries symbols); "
                               f"if the pack has an [on-screen] line with it add checked_against: 'screen', else mark origin 'derived'")
                if b["type"] == "diagram":
                    for e in check_diagram(b):
                        r.err(f"{where}: {e}")
                if b["type"] != "text":
                    visual = True
                elif len(b["text"].split()) > 90:
                    r.err(f"{where}: text block is {len(b['text'].split())} words (max 90): split it or use cards/steps")
        if not cites:
            r.err(f"screen {s['id']}: no timestamp citation anywhere on the screen")
        if not visual:
            r.err(f"screen {s['id']}: only plain text blocks; add cards/steps/quote/callout (rubric: visual first)")
    for t in _lesson_texts(les):
        lesson_words += len(re.sub(r"\[\[|\]\]", "", t).split())
    if lesson_words and quote_words / (lesson_words + quote_words) > MAX_QUOTES_SHARE:
        r.err(f"quotes are {quote_words / (lesson_words + quote_words):.0%} of the lesson (max {MAX_QUOTES_SHARE:.0%}): paraphrase more")
    if not any(b["type"] == "quote" for s in les["screens"] for b in s["blocks"]):
        r.warn("no quote block (speaker <-> plain-language translation); the module needs at least one")
    if not any(b["type"] == "diagram" for s in les["screens"] for b in s["blocks"]):
        r.warn("no diagram in this lesson; add one where the idea is a process or a function (rubric: visual)")
    if sum(1 for s in les["screens"] for b in s["blocks"] if b["type"] == "callout") > 2:
        r.warn("more than 2 callouts in one lesson")

    # long verbatim copying outside quote blocks
    src = " ".join(_window_text(work, vid, a + SLACK, b - SLACK) for a, b in windows)
    sh = _shingles(src, 12)
    for t in _lesson_texts(les):
        w = _wordlist(re.sub(r"\[\[|\]\]", "", t))
        run = best = 0
        for i in range(len(w) - 11):
            if tuple(w[i:i + 12]) in sh:
                run += 1
                best = max(best, run)
            else:
                run = 0
        if best:
            n = best + 11
            (r.err if n >= 25 else r.warn)(f"{n}-word run copied from the transcript outside a quote block: {t[:60]!r}...")

    for where, t in _all_strings(les):
        if "$$" in t:
            r.err(f"{where}: '$$' is not allowed in running text; use a math block for display formulas")
            continue
        if unescaped_dollars(t) % 2:
            r.err(f"{where}: unbalanced $ (write a literal dollar as \\$): {t[:50]!r}")
            continue
        for kind, sg in split_math(t):
            if kind == "math":
                for e in check_latex(sg, display=False):
                    r.err(f"{where}: inline math ${sg[:40]}$: {e}")
    for g in les["glossary"]:
        if "$" in g["definition"] or "$" in g["term"]:
            r.err(f"glossary '{g['term']}': tooltips are plain text; describe the formula in words")

    for i, q in enumerate(les["quiz"]):
        if q["answer"] >= len(q["options"]):
            r.err(f"quiz[{i}]: answer index {q['answer']} out of range")
        if len({o.strip().lower() for o in q["options"]}) != len(q["options"]):
            r.err(f"quiz[{i}]: duplicate options")
        if MEMORY_Q.match(q["question"].strip()):
            r.warn(f"quiz[{i}]: tests recall, not application: {q['question'][:50]!r}")
        check_times(q["cite"], f"quiz[{i}]")
    if len(les["quiz"]) >= 3 and len({q["answer"] for q in les["quiz"]}) == 1:
        r.warn("every quiz answer has the same position; vary it")

    gl = {g["term"].strip().lower(): g for g in les["glossary"]}
    for g in les["glossary"]:
        check_times(g["cite"], f"glossary '{g['term']}'")
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


# ── course ───────────────────────────────────────────────────────────────


def validate_course(work: Work) -> list[Result]:
    results = [validate_outline(work)]
    if results[0].errors:
        return results
    outline = read_json(work.outline)
    for m in outline["modules"]:
        quotes = 0
        for lsn in m["lessons"]:
            res = validate_lesson(work, lsn["id"])
            results.append(res)
            if not res.errors:
                les = read_json(work.drafts / f"{lsn['id']}.json")
                quotes += sum(1 for s in les["screens"] for b in s["blocks"] if b["type"] == "quote")
        if quotes == 0 and all((work.drafts / f"{lsn['id']}.json").exists() for lsn in m["lessons"]):
            r = Result(m["id"])
            r.err(f"module {m['id']} has no quote block in any lesson (at least one speaker <-> plain words block per module)")
            results.append(r)
    return results


def usage_summary(work: Work) -> dict:
    tot: dict[str, int] = {}
    if work.usage.exists():
        for ln in work.usage.read_text(encoding="utf-8").splitlines():
            d = json.loads(ln)
            tot[d["kind"] + "_tokens"] = tot.get(d["kind"] + "_tokens", 0) + d["tokens"]
    if work.digest.exists():
        from .common import est_tokens
        tot["digest_tokens"] = est_tokens(work.digest.read_text(encoding="utf-8"))
    return tot


def write_report(work: Work, results: list[Result]) -> dict:
    rep = {"ok": not any(r.errors for r in results), "results": [r.as_dict() for r in results], "usage": usage_summary(work)}
    write_json(work.report, rep)
    return rep


def run_validate(work: Work, stage: str, lesson: str | None) -> int:
    if stage == "outline":
        results = [validate_outline(work)]
    elif stage == "lesson":
        if not lesson:
            raise SystemExit("--lesson L-01 is required for --stage lesson")
        results = [validate_lesson(work, lesson)]
    else:
        results = validate_course(work)
    rep = write_report(work, results)
    for r in results:
        tag = "ok" if not r.errors else "FAIL"
        print(f"[{tag}] {r.scope}: {len(r.errors)} errors, {len(r.warnings)} warnings")
        for e in r.errors:
            print(f"    ERROR   {e}")
        for w in r.warnings:
            print(f"    warning {w}")
    print("usage (estimated tokens):", rep["usage"])
    return 0 if rep["ok"] else 1


def status(work: Work) -> str:
    out = []
    out.append(f"videos.json: {'yes' if work.videos.exists() else 'NO -> run prepare'}")
    out.append(f"manifest.json: {'yes' if work.manifest.exists() else 'NO -> run prepare'}")
    out.append(f"digest_all.md: {'yes' if work.digest.exists() else 'NO -> run digest'}")
    if not work.outline.exists():
        out.append("outline.json: NO -> Pass 1: read digest_all.md, write outline.json, validate --stage outline")
        return "\n".join(out)
    ov = validate_outline(work)
    out.append(f"outline.json: {'valid' if not ov.errors else f'INVALID ({len(ov.errors)} errors) -> validate --stage outline'}")
    if ov.errors:
        return "\n".join(out)
    for _m, lsn in _lessons(read_json(work.outline)):
        lid = lsn["id"]
        if (work.drafts / f"{lid}.json").exists():
            st = "validated" if not validate_lesson(work, lid).errors else "draft-invalid"
        elif (work.selections / f"{lid}.md").exists():
            st = "pack-ready"
        else:
            st = "todo"
        out.append(f"  {lid}: {st}  {lsn['title']}")
    return "\n".join(out)
