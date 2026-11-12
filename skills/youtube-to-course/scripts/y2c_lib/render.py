"""Stage 8 — render validated lesson drafts into the course HTML (timestamps link to youtu.be).

course/  course.css course-ui.js [course-math.js] _base.html _footer.html  modules/NN-slug.html  index.html
The assets are copied byte-for-byte from assets/ (never regenerated). Only module HTML is produced here.
"""
from __future__ import annotations

import html
import itertools
import re
import shutil
from pathlib import Path

from .common import Work, read_json, slugify
from . import diagrams, ui
from .mathtex import split_math

ASSETS = Path(__file__).resolve().parents[2] / "assets"
from .common import fmt_time, yt_link  # noqa: E402
L10N = {
    "en": {"objectives": "By the end of this lesson you can:", "why": "Why care?", "metaphor": "Think of it like this",
           "from_src": "FROM THE VIDEO", "plain": "IN PLAIN WORDS", "takeaways": "Key takeaways", "quiz": "Check yourself",
           "check": "Check answers", "retry": "Try again", "right": "Correct.", "wrong": "Not quite.", "pick": "Choose an answer first.", "sources": "Sources", "glossary": "Glossary",
           "glossary_sub": "Every term explained in the course, with the moment in the video it comes from.",
           "derived": "derived here, not shown in the video", "diagram": "Illustration made for this course", "symbols": "Symbols",
           "watch": "Watch", "method": "Built from {title}. Timestamps (▶ m:ss) open the source video at that moment; they are accurate to a few seconds."},
    "ru": {"objectives": "После этого урока вы сможете:", "why": "Зачем это нужно?", "metaphor": "Представьте так",
           "from_src": "ИЗ ВИДЕО", "plain": "ПРОСТЫМИ СЛОВАМИ", "takeaways": "Главное", "quiz": "Проверьте себя",
           "check": "Проверить ответы", "retry": "Ещё раз", "right": "Верно.", "wrong": "Не совсем.", "pick": "Сначала выберите ответ.", "sources": "Источники", "glossary": "Глоссарий",
           "glossary_sub": "Все термины курса с моментом видео, откуда они взяты.",
           "derived": "выведено здесь, в видео этого нет", "diagram": "Иллюстрация для этого курса", "symbols": "Обозначения",
           "watch": "Смотреть", "method": "Курс построен по материалам: {title}. Метки времени (▶ м:сс) открывают видео в нужный момент; точность — несколько секунд."},
}

def esc(s: str) -> str:
    return html.escape(s, quote=True)


def _math_span(tex: str, display: bool = False) -> str:
    d = '$$' if display else '$'
    return f'<span class="tex"{" data-display=\"1\"" if display else ""} data-tex="{esc(tex)}">{d}{esc(tex)}{d}</span>'


def plain_markup(text: str) -> str:
    """Escape text and turn $..$ into KaTeX placeholders (no glossary tooltips)."""
    return "".join(_math_span(seg) if k == "math" else esc(seg) for k, seg in split_math(text))


def cite_chip(times: list[int], lang: str, yt_id: str) -> str:
    """One ▶ m:ss link per distinct moment (at most 3; the first, middle and last when there are more)."""
    ts = sorted(set(times))
    if not ts:
        return ""
    if len(ts) > 3:
        ts = [ts[0], ts[len(ts) // 2], ts[-1]]
    return "".join(f'<a class="src-ref" href="{esc(yt_link(yt_id, t))}" target="_blank" rel="noopener" '
                   f'title="{esc(L10N[lang]["watch"])} {fmt_time(t)}">▶ {fmt_time(t)}</a>' for t in ts)


class TermState:
    """Tooltip each glossary term only on its first appearance within a module."""

    def __init__(self, glossary: dict[str, str], uid=None):
        self.gl, self.seen = glossary, set()
        self.uid = uid if uid is not None else itertools.count(1)

    def markup(self, text: str) -> str:
        return "".join(_math_span(seg) if k == "math" else self._terms(seg) for k, seg in split_math(text))

    def _terms(self, text: str) -> str:
        e = esc(text)

        def sub(m):
            raw = html.unescape(m.group(1))
            k = raw.strip().lower()
            if k in self.gl and k not in self.seen:
                self.seen.add(k)
                return (f'<span class="term" tabindex="0">{esc(raw)}<span class="gloss" role="tooltip"><b>{esc(raw)}</b> {esc(self.gl[k])}</span></span>')
            return esc(raw)

        return re.sub(r"\[\[(.+?)\]\]", sub, e)


def _block(b: dict, ts: TermState, lang: str, src: dict) -> str:
    L = L10N[lang]
    t = b["type"]
    yt = src["yt_id"]
    if t == "text":
        return f'<p>{ts.markup(b["text"])}{cite_chip(b["cite"], lang, yt)}</p>'
    if t == "cards":
        cards = "".join(f'<div class="pattern-card"><h4 class="pattern-title">{ts.markup(it["title"])}</h4>'
                        f'<p class="pattern-desc">{ts.markup(it["text"])}</p></div>' for it in b["items"])
        return f'<div class="pattern-cards">{cards}</div>{_cite_line(b["cite"], lang)}'
    if t == "steps":
        steps = "".join(
            f'<div class="step-card"><div class="step-num">{i + 1}</div><div class="step-body">'
            f'<strong>{ts.markup(it["title"])}</strong><p>{ts.markup(it["text"])}</p></div></div>'
            for i, it in enumerate(b["items"]))
        return f'<div class="step-cards">{steps}</div>{_cite_line(b["cite"], lang, yt)}'
    if t == "quote":
        who = b.get("speaker") or src.get("channel") or ""
        return (f'<div class="translation-block quote"><div class="translation-code">'
                f'<span class="translation-label">{L["from_src"]}</span>'
                f'<div class="quote-body">«{esc(b["text"])}»</div>'
                f'<span class="quote-attrib">— {esc(who)}, {esc(src["title"][:60])} {cite_chip([b["at"]], lang, yt)}</span></div>'
                f'<div class="translation-english"><span class="translation-label">{L["plain"]}</span>'
                f'<div class="translation-lines"><p class="tl">{ts.markup(b["meaning"])}</p></div></div></div>')
    if t == "diagram":
        svg = diagrams.render_svg(b, f"d{next(ts.uid)}")
        return (f'<figure class="diagram"><p class="fig-title">{esc(b["title"])}</p>{svg}'
                f'<figcaption><span class="fig-tag">{L["diagram"]}</span>{ts.markup(b["caption"])}{cite_chip(b["cite"], lang, yt)}</figcaption></figure>')
    if t == "math":
        sym = "".join(f'<dt>{_math_span(sy["sym"])}</dt><dd>{ts.markup(sy["meaning"])}</dd>' for sy in b["symbols"])
        cap = f'<figcaption>{ts.markup(b["caption"])}</figcaption>' if b.get("caption") else ""
        badge = f'<span class="origin-badge">{L["derived"]}</span>' if b["origin"] == "derived" else ""
        return (f'<figure class="math-block"><div class="math-eq">{_math_span(b["latex"], display=True)}</div>{cap}'
                f'<dl class="symbol-list" aria-label="{L["symbols"]}">{sym}</dl>'
                f'<p class="math-meta">{badge}{cite_chip(b["cite"], lang, yt)}</p></figure>')
    if t == "callout":
        v = b["variant"]
        return (f'<div class="callout callout-{v}"><div class="callout-content">'
                f'<strong class="callout-title">{ts.markup(b["title"])}</strong>'
                f'<p>{ts.markup(b["text"])}{cite_chip(b["cite"], lang, yt)}</p></div></div>')
    raise ValueError(f"unknown block type {t}")


def _cite_line(times: list[int], lang: str, yt: str) -> str:
    chip = cite_chip(times, lang, yt)
    return f'<p>{chip}</p>' if chip else ""


def _quiz(lesson: dict, lang: str) -> str:
    L = L10N[lang]
    qid = f"quiz-{lesson['id'].lower()}"
    blocks = []
    for n, q in enumerate(lesson["quiz"]):
        opts = "".join(f'<label class="quiz-option"><input type="radio" name="{qid}-{n}" value="opt-{i}"><span>{esc(o)}</span></label>'
                       for i, o in enumerate(q["options"]))
        blocks.append(
            f'<fieldset class="quiz-question-block" data-correct="opt-{q["answer"]}" '
            f'data-explanation-right="{esc(plain_markup(q["explain_right"]))} (▶ {", ".join(fmt_time(x) for x in sorted(set(q["cite"]))[:3])})" '
            f'data-explanation-wrong="{esc(plain_markup(q["explain_wrong"]))}">'
            f'<legend class="quiz-question">{plain_markup(q["question"])}</legend><div class="quiz-options">{opts}</div>'
            f'<div class="quiz-feedback"></div></fieldset>')
    return (f'<div class="quiz-container" id="{qid}" data-right="{esc(L["right"])}" data-wrong="{esc(L["wrong"])}" data-pick="{esc(L["pick"])}">'
            f'{"".join(blocks)}<div class="quiz-actions"><button type="button" class="quiz-check-btn">{L["check"]}</button>'
            f'<button type="button" class="quiz-reset-btn" hidden>{L["retry"]}</button></div></div>')


def render_lesson(spec: dict, les: dict, ts: TermState, lang: str, src: dict, segs: dict) -> str:
    L = L10N[lang]
    out = []
    objs = "".join(f"<li>{esc(o)}</li>" for o in spec["objectives"])
    out.append(
        f'<section class="screen" id="{esc(spec["id"].lower())}">'
        f'<h2 class="screen-heading"><span class="lesson-label">{esc(spec["id"])}</span>{esc(les["title"])}</h2>'
        f'<p class="lesson-hook">{ts.markup(les["hook"])}</p>'
        f'<div class="callout callout-accent"><div class="callout-content">'
        f'<strong class="callout-title">{L["metaphor"]}</strong><p>{ts.markup(les["metaphor"])}</p></div></div>'
        f'<div class="callout callout-info"><div class="callout-content">'
        f'<strong class="callout-title">{L["why"]}</strong><p>{ts.markup(les["why_care"])}</p>'
        f'<p><strong>{L["objectives"]}</strong></p><ul class="objective-list">{objs}</ul></div></div></section>')
    for s in les["screens"]:
        body = "\n".join(_block(b, ts, lang, src) for b in s["blocks"])
        out.append(f'<section class="screen"><h2 class="screen-heading">{ts.markup(s["heading"])}</h2>\n{body}</section>')
    take = "".join(
        f'<div class="step-card"><div class="step-num">{i + 1}</div><div class="step-body"><p>{ts.markup(t)}</p></div></div>'
        for i, t in enumerate(les["key_takeaways"]))
    srcs = ", ".join(f'{fmt_time(segs[c]["start"])}–{fmt_time(segs[c]["end"])} {segs[c]["title"]}' for c in les["sources"]["segments"] if c in segs)
    out.append(
        f'<section class="screen"><h2 class="screen-heading">{L["takeaways"]}</h2>'
        f'<div class="step-cards">{take}</div>'
        f'<h2 class="screen-heading" style="margin-top:3rem">{L["quiz"]}</h2>{_quiz(les, lang)}'
        f'<p class="method-note">{L["sources"]}: {esc(srcs)} {cite_chip([segs[les["sources"]["segments"][0]]["start"]], lang, src["yt_id"])}</p></section>')
    return "\n".join(out)


KATEX = "0.16.11"
MATH_JS = """/* book-to-course: renders <span class="tex" data-tex="..."> with KaTeX; works for content added later (quiz feedback). */
(function () {
  function renderAll() {
    if (!window.katex) return; // KaTeX CDN unreachable: the raw $TeX$ stays visible
    document.querySelectorAll('.tex:not([data-done])').forEach(function (el) {
      el.setAttribute('data-done', '1');
      try {
        window.katex.render(el.getAttribute('data-tex'), el,
          { displayMode: el.getAttribute('data-display') === '1', throwOnError: false, strict: 'ignore', trust: false });
      } catch (e) { /* leave the raw source */ }
    });
  }
  function init() { renderAll(); new MutationObserver(renderAll).observe(document.body, { childList: true, subtree: true }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
"""


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Fira+Mono&family=Spectral+SC:wght@500;600&family=Spectral:ital,wght@0,400;0,600;0,700;1,400&display=swap" rel="stylesheet">')


def init_course(work: Work, course_dir: Path, outline: dict, has_math: bool = False, toc_html: str = "") -> None:
    course_dir.mkdir(parents=True, exist_ok=True)
    (course_dir / "modules").mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "course.css", course_dir / "course.css")
    (course_dir / "course-ui.js").write_text(ui.UI_JS, encoding="utf-8")
    title = outline["course"].get("course_title") or outline["course"]["title"]
    accent = outline.get("accent", ui.DEFAULT_PEN)
    (course_dir / "_base.html").write_text(
        ui.base_html(outline["course"]["lang"], title, accent, toc_html, has_math, KATEX, FONTS), encoding="utf-8")
    (course_dir / "_footer.html").write_text(ui.FOOTER, encoding="utf-8")
    if has_math:  # KaTeX from the CDN (like the Google Fonts above); offline -> raw TeX shown
        (course_dir / "course-math.js").write_text(MATH_JS, encoding="utf-8")
    elif (course_dir / "course-math.js").exists():
        (course_dir / "course-math.js").unlink()


def render(work: Work, course_dir: Path, partial: bool = False) -> dict:
    from .validate import validate_course

    outline, manifest = read_json(work.outline), read_json(work.manifest)
    lang = outline["course"]["lang"]
    segs = {s["id"]: s for s in manifest["segments"]}
    vids = {v["id"]: v for v in manifest["videos"]}
    if not partial:
        bad = [r for r in validate_course(work) if r.errors]
        if bad:
            raise SystemExit("validation failed (run `validate`): " + "; ".join(f"{r.scope}: {r.errors[0]}" for r in bad[:3]))
    plan = []
    for m in outline["modules"]:
        ls = [(lsn, read_json(work.drafts / f"{lsn['id']}.json")) for lsn in m["lessons"] if (work.drafts / f"{lsn['id']}.json").exists()]
        if ls:
            plan.append((m, ls))
    n_mod = len(plan)
    L = L10N[lang]
    files: dict[str, str] = {}
    uid = itertools.count(1)  # deterministic ids for SVG markers/clip paths
    all_terms: dict[str, tuple[str, str, list[int], str]] = {}
    for i, (m, ls) in enumerate(plan, start=1):
        src = vids[m["video"]]
        gl: dict[str, str] = {}
        for _, les in ls:
            for g in les["glossary"]:
                gl.setdefault(g["term"].strip().lower(), g["definition"])
                all_terms.setdefault(g["term"].strip().lower(), (g["term"], g["definition"], g["cite"], src["yt_id"]))
        ts = TermState(gl, uid)
        body = "\n".join(render_lesson(spec, les, ts, lang, src, segs) for spec, les in ls)
        sec = (f'<section class="module" id="module-{i}">\n  <div class="module-content">\n'
               f'    <header class="module-header"><span class="module-number">{i:02d}</span>'
               f'<h1 class="module-title">{esc(m["title"])}</h1><p class="module-subtitle">{esc(m["subtitle"])}</p></header>\n'
               f'    <div class="module-body">\n{body}\n    </div>\n  </div>\n</section>\n')
        files[f"{i:02d}-{slugify(m['title'])}.html"] = sec
    scope = manifest["scope"]
    title = scope.get("title") or manifest["videos"][0]["title"]
    items = "".join(f'<dt>{esc(t)}{cite_chip(c[:1], lang, yt)}</dt><dd>{esc(d)}</dd>'
                    for _, (t, d, c, yt) in sorted(all_terms.items(), key=lambda kv: kv[0]))
    files["99-glossary.html"] = (
        f'<section class="module" id="module-{n_mod + 1}">\n  <div class="module-content">\n'
        f'    <header class="module-header"><span class="module-number">{n_mod + 1:02d}</span>'
        f'<h1 class="module-title">{L["glossary"]}</h1><p class="module-subtitle">{L["glossary_sub"]}</p></header>\n'
        f'    <div class="module-body"><section class="screen"><dl class="glossary-list">{items}</dl>'
        f'<p class="method-note">{esc(L["method"].format(title=title))}</p></section></div>\n  </div>\n</section>\n')
    course_title = outline["course"].get("course_title") or outline["course"]["title"]
    mods = [{"n": i, "title": m["title"], "subtitle": m["subtitle"],
             "lessons": [{"id": spec["id"].lower(), "title": les["title"]} for spec, les in ls]} for i, (m, ls) in enumerate(plan, start=1)]
    stats = {"lessons": sum(len(m["lessons"]) for m in mods), "quiz": sum(len(les["quiz"]) for _, ls in plan for _, les in ls), "terms": len(all_terms)}
    if scope["kind"] == "playlist":
        span = f"{len(manifest['videos'])} videos"
    else:
        a, b = manifest["videos"][0]["scope"]
        span = f"{fmt_time(a)}–{fmt_time(b)}"
    files["00-cover.html"] = ui.build_cover(lang, course_title, title, (span, ""), mods, stats)
    toc_html = ui.build_toc(lang, course_title, mods, len(all_terms))
    has_math = any('class="tex"' in h for h in files.values())
    init_course(work, course_dir, {"course": outline["course"], "accent": outline.get("accent", "indigo")}, has_math=has_math, toc_html=toc_html)
    for old in (course_dir / "modules").glob("*.html"):
        old.unlink()
    for name, h in files.items():
        (course_dir / "modules" / name).write_text(h, encoding="utf-8")
    assemble(course_dir)
    return {"modules": n_mod, "lessons": sum(len(ls) for _, ls in plan), "glossary_terms": len(all_terms), "math": has_math,
            "index": str(course_dir / "index.html")}


def assemble(course_dir: Path) -> None:
    parts = [(course_dir / "_base.html").read_text(encoding="utf-8")]
    parts += [p.read_text(encoding="utf-8") for p in sorted((course_dir / "modules").glob("*.html"))]
    parts.append((course_dir / "_footer.html").read_text(encoding="utf-8"))
    (course_dir / "index.html").write_text("".join(parts), encoding="utf-8")
