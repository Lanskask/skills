"""Stage 8 — render validated lesson drafts into the codebase-to-course HTML layout (timestamps link to youtu.be).

course/  styles.css main.js course-extras.css _base.html _footer.html build.sh  modules/NN-slug.html  index.html
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
ACCENTS = {
    "vermillion": ("#D94F30", "#C4432A", "#FDEEE9", "#E8836C"),
    "coral": ("#E06B56", "#C85A47", "#FDECEA", "#E89585"),
    "teal": ("#2A7B9B", "#1F6280", "#E4F2F7", "#5A9DB8"),
    "amber": ("#D4A843", "#BF9530", "#FDF5E0", "#E0C070"),
    "forest": ("#2D8B55", "#226B41", "#E8F5EE", "#5AAD7A"),
}
ICONS = {"accent": "💡", "info": "📌", "warning": "⚠️"}
L10N = {
    "en": {"objectives": "By the end of this lesson you can:", "why": "Why care?", "metaphor": "Think of it like this",
           "from_src": "FROM THE VIDEO", "plain": "IN PLAIN WORDS", "takeaways": "Key takeaways", "quiz": "Check yourself",
           "check": "Check Answers", "retry": "Try Again", "sources": "Sources", "glossary": "Glossary",
           "glossary_sub": "Every term explained in the course, with the moment in the video it comes from.",
           "derived": "derived here, not shown in the video", "diagram": "Illustration made for this course", "symbols": "Symbols",
           "watch": "Watch", "method": "Built from {title}. Timestamps (▶ m:ss) open the source video at that moment; they are accurate to a few seconds."},
    "ru": {"objectives": "После этого урока вы сможете:", "why": "Зачем это нужно?", "metaphor": "Представьте так",
           "from_src": "ИЗ ВИДЕО", "plain": "ПРОСТЫМИ СЛОВАМИ", "takeaways": "Главное", "quiz": "Проверьте себя",
           "check": "Проверить ответы", "retry": "Ещё раз", "sources": "Источники", "glossary": "Глоссарий",
           "glossary_sub": "Все термины курса с моментом видео, откуда они взяты.",
           "derived": "выведено здесь, в видео этого нет", "diagram": "Иллюстрация для этого курса", "symbols": "Обозначения",
           "watch": "Смотреть", "method": "Курс построен по материалам: {title}. Метки времени (▶ м:сс) открывают видео в нужный момент; точность — несколько секунд."},
}

EXTRA_CSS = diagrams.CSS + """/* youtube-to-course additions. Only adds classes that codebase-to-course does not have. */
a.src-ref { text-decoration: none; }
a.src-ref:hover { background: var(--color-accent); color: #fff; }
.src-ref { display: inline-block; margin-left: .4em; padding: 0 .45em; font-size: .72em; line-height: 1.7;
  font-family: var(--font-mono, monospace); color: var(--color-accent-text); background: var(--color-accent-light);
  border-radius: 999px; vertical-align: .15em; white-space: nowrap; }
.lesson-label { display: block; font-size: var(--text-sm, .875rem); letter-spacing: .08em; text-transform: uppercase;
  color: var(--color-accent-text); font-weight: 600; margin-bottom: .5rem; }
.translation-block.quote .quote-body { font-family: var(--font-body, serif); font-style: italic; font-size: 1.05rem;
  line-height: 1.6; white-space: normal; }
.translation-block.quote .quote-attrib { display: block; margin-top: 1rem; font-size: .8rem; opacity: .75; font-style: normal;
  font-family: var(--font-mono, monospace); }
.objective-list { margin: 1rem 0 0 1.2rem; }
.objective-list li { margin-bottom: .4rem; }
.glossary-list dt { font-family: var(--font-display); font-weight: 600; margin-top: 1rem; }
.glossary-list dd { margin: .2rem 0 0 0; color: var(--color-text-secondary); }
.tl-at { display: inline-block; margin-right: .4em; padding: 0 .5em; font-size: .72em; font-family: var(--font-mono, monospace);
  color: var(--color-accent-text); background: var(--color-accent-light); border-radius: 999px; }
.code-note { margin-top: -1rem; font-size: .88rem; color: var(--color-text-secondary); }
.task-card { margin: 1.5rem 0; padding: 1.25rem 1.5rem; background: var(--color-surface); border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm); border-left: 3px solid var(--color-accent); }
.task-card .task-label { display: block; font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: var(--color-accent-text); font-weight: 600; }
.task-card .task-statement { margin: .5rem 0; font-style: italic; white-space: pre-wrap; }
.task-card details { margin-top: .75rem; } .task-card summary { cursor: pointer; color: var(--color-accent-text); }
.math-block { margin: 2rem 0; padding: 1.25rem 1.5rem; background: var(--color-surface); border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm); border-left: 3px solid var(--color-accent); }
.math-eq { overflow-x: auto; padding: .5rem 0; text-align: center; font-size: 1.15rem; }
.math-block figcaption { margin-top: .5rem; font-size: .9rem; color: var(--color-text-secondary); }
.symbol-list { display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1rem; margin: 1rem 0 0; font-size: .95rem; }
.symbol-list dt { font-weight: 400; margin: 0; } .symbol-list dd { margin: 0; color: var(--color-text-secondary); }
.origin-badge { display: inline-block; padding: 0 .55em; font-size: .72em; line-height: 1.8; border-radius: 999px;
  background: var(--color-info-light); color: var(--color-info); }
.math-meta { margin: .75rem 0 0; }
.tex .katex-error { color: var(--color-error); font-family: var(--font-mono, monospace); }
.method-note { margin-top: 3rem; font-size: .85rem; color: var(--color-text-secondary); }
"""


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
                return f'<span class="term" data-definition="{esc(self.gl[k])}">{esc(raw)}</span>'
            return esc(raw)

        return re.sub(r"\[\[(.+?)\]\]", sub, e)


def _block(b: dict, ts: TermState, lang: str, src: dict) -> str:
    L = L10N[lang]
    t = b["type"]
    yt = src["yt_id"]
    if t == "text":
        return f'<p>{ts.markup(b["text"])}{cite_chip(b["cite"], lang, yt)}</p>'
    if t == "cards":
        cards = []
        for i, it in enumerate(b["items"]):
            icon = f'<div class="pattern-icon" style="background: var(--color-actor-{i % 5 + 1})">{esc(it.get("icon", "•"))}</div>' if it.get("icon") else ""
            cards.append(f'<div class="pattern-card" style="border-top: 3px solid var(--color-actor-{i % 5 + 1})">{icon}'
                         f'<h4 class="pattern-title">{ts.markup(it["title"])}</h4>'
                         f'<p class="pattern-desc">{ts.markup(it["text"])}</p></div>')
        return f'<div class="pattern-cards stagger-children">{"".join(cards)}</div>{_cite_line(b["cite"], lang, yt)}'
    if t == "steps":
        steps = "".join(
            f'<div class="step-card"><div class="step-num">{i + 1}</div><div class="step-body">'
            f'<strong>{ts.markup(it["title"])}</strong><p>{ts.markup(it["text"])}</p></div></div>'
            for i, it in enumerate(b["items"]))
        return f'<div class="step-cards">{steps}</div>{_cite_line(b["cite"], lang, yt)}'
    if t == "quote":
        who = b.get("speaker") or src.get("channel") or ""
        return (f'<div class="translation-block quote animate-in"><div class="translation-code">'
                f'<span class="translation-label">{L["from_src"]}</span>'
                f'<div class="quote-body">«{esc(b["text"])}»</div>'
                f'<span class="quote-attrib">— {esc(who)}, {esc(src["title"][:60])} {cite_chip([b["at"]], lang, yt)}</span></div>'
                f'<div class="translation-english"><span class="translation-label">{L["plain"]}</span>'
                f'<div class="translation-lines"><p class="tl">{ts.markup(b["meaning"])}</p></div></div></div>')
    if t == "diagram":
        svg = diagrams.render_svg(b, f"d{next(ts.uid)}")
        return (f'<figure class="diagram animate-in"><p class="fig-title">{esc(b["title"])}</p>{svg}'
                f'<figcaption><span class="fig-tag">{L["diagram"]}</span>{ts.markup(b["caption"])}{cite_chip(b["cite"], lang, yt)}</figcaption></figure>')
    if t == "math":
        sym = "".join(f'<dt>{_math_span(sy["sym"])}</dt><dd>{ts.markup(sy["meaning"])}</dd>' for sy in b["symbols"])
        cap = f'<figcaption>{ts.markup(b["caption"])}</figcaption>' if b.get("caption") else ""
        badge = f'<span class="origin-badge">{L["derived"]}</span>' if b["origin"] == "derived" else ""
        return (f'<figure class="math-block animate-in"><div class="math-eq">{_math_span(b["latex"], display=True)}</div>{cap}'
                f'<dl class="symbol-list" aria-label="{L["symbols"]}">{sym}</dl>'
                f'<p class="math-meta">{badge}{cite_chip(b["cite"], lang, yt)}</p></figure>')
    if t == "callout":
        v = b["variant"]
        return (f'<div class="callout callout-{v}"><div class="callout-icon">{ICONS[v]}</div><div class="callout-content">'
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
    for q in lesson["quiz"]:
        opts = "".join(
            f'<button class="quiz-option" data-value="opt-{i}" onclick="selectOption(this)">'
            f'<div class="quiz-option-radio"></div><span>{esc(o)}</span></button>' for i, o in enumerate(q["options"]))
        blocks.append(
            f'<div class="quiz-question-block" data-correct="opt-{q["answer"]}" '
            f'data-explanation-right="{esc(plain_markup(q["explain_right"]))} (▶ {", ".join(fmt_time(x) for x in sorted(set(q["cite"]))[:3])})" '
            f'data-explanation-wrong="{esc(plain_markup(q["explain_wrong"]))}">'
            f'<h3 class="quiz-question">{plain_markup(q["question"])}</h3><div class="quiz-options">{opts}</div>'
            f'<div class="quiz-feedback"></div></div>')
    return (f'<div class="quiz-container" id="{qid}">{"".join(blocks)}'
            f'<button class="quiz-check-btn" onclick="checkQuiz(\'{qid}\')">{L["check"]}</button>'
            f'<button class="quiz-reset-btn" onclick="resetQuiz(\'{qid}\')">{L["retry"]}</button></div>')


def render_lesson(spec: dict, les: dict, ts: TermState, lang: str, src: dict, segs: dict) -> str:
    L = L10N[lang]
    out = []
    objs = "".join(f"<li>{esc(o)}</li>" for o in spec["objectives"])
    out.append(
        f'<section class="screen animate-in" id="{esc(spec["id"].lower())}">'
        f'<span class="lesson-label">{esc(spec["id"])}</span><h2 class="screen-heading">{esc(les["title"])}</h2>'
        f'<p>{ts.markup(les["hook"])}</p>'
        f'<div class="callout callout-accent"><div class="callout-icon">🧭</div><div class="callout-content">'
        f'<strong class="callout-title">{L["metaphor"]}</strong><p>{ts.markup(les["metaphor"])}</p></div></div>'
        f'<div class="callout callout-info"><div class="callout-icon">🎯</div><div class="callout-content">'
        f'<strong class="callout-title">{L["why"]}</strong><p>{ts.markup(les["why_care"])}</p>'
        f'<p><strong>{L["objectives"]}</strong></p><ul class="objective-list">{objs}</ul></div></div></section>')
    for s in les["screens"]:
        body = "\n".join(_block(b, ts, lang, src) for b in s["blocks"])
        out.append(f'<section class="screen animate-in"><h2 class="screen-heading">{ts.markup(s["heading"])}</h2>\n{body}</section>')
    take = "".join(
        f'<div class="step-card"><div class="step-num">{i + 1}</div><div class="step-body"><p>{ts.markup(t)}</p></div></div>'
        for i, t in enumerate(les["key_takeaways"]))
    srcs = ", ".join(f'{fmt_time(segs[c]["start"])}–{fmt_time(segs[c]["end"])} {segs[c]["title"]}' for c in les["sources"]["segments"] if c in segs)
    out.append(
        f'<section class="screen animate-in"><h2 class="screen-heading">{L["takeaways"]}</h2>'
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


def init_course(work: Work, course_dir: Path, outline: dict, module_titles: list[tuple[int, str]],
                has_math: bool = False, toc_html: str = "") -> None:
    course_dir.mkdir(parents=True, exist_ok=True)
    (course_dir / "modules").mkdir(exist_ok=True)
    for f in ("styles.css", "main.js", "_footer.html", "build.sh"):
        shutil.copyfile(ASSETS / f, course_dir / f)
    accent_name = outline.get("accent", "teal")
    (course_dir / "course-extras.css").write_text(EXTRA_CSS + ui.ui_css(accent_name, ACCENTS[accent_name]), encoding="utf-8")
    (course_dir / "course-ui.js").write_text(ui.UI_JS, encoding="utf-8")
    base = (ASSETS / "_base.html").read_text(encoding="utf-8")
    title = outline["course"].get("course_title") or outline["course"]["title"]
    ac = ACCENTS[accent_name]
    ac = (ui.ensure_white_contrast(ac[0]), ui.ensure_white_contrast(ac[1], 5.2), ac[2], ac[3])   # white text on accent fills must reach WCAG AA
    lang = outline["course"]["lang"]
    # chrome: Home + Contents buttons, theme toggle, skip link, contents drawer, no-flash theme script, no-JS fallback
    base = base.replace('<span class="nav-title">COURSE_TITLE</span>', ui.nav_left(lang, title))
    base = re.sub(r"NAV_DOTS\s*</div>", lambda m: "NAV_DOTS\n      </div>\n      " + ui.nav_actions(lang), base, count=1)
    base = base.replace("</nav>", "</nav>\n" + toc_html, 1)
    base = base.replace("<body>", f'<body>\n  <a class="skip-link" href="#main">{ui.TEXT[lang]["skip"]}</a>', 1)
    base = base.replace('<meta name="viewport" content="width=device-width, initial-scale=1.0">',
                        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <meta name="color-scheme" content="light dark">\n  '
                        + ui.INLINE_THEME_JS, 1)
    base = base.replace("</head>", "  <noscript><style>.animate-in{opacity:1;transform:none}</style></noscript>\n</head>", 1)
    base = base.replace('<script src="main.js" defer></script>', '<script src="main.js" defer></script>\n  <script src="course-ui.js" defer></script>', 1)
    base = re.sub(r"<!--\s*One <button> per module.*?-->\s*", "", base, flags=re.S)   # template instructions, not for the output
    base = base.replace('role="tablist"', 'role="group" aria-label="' + ("Modules" if lang == "en" else "Модули") + '"')
    dots = "\n        ".join(
        f'<button class="nav-dot" data-target="module-{n}" data-tooltip="{esc(t)}" aria-label="Module {n}: {esc(t)}"></button>'
        for n, t in module_titles)
    base = (base.replace("COURSE_TITLE", esc(title)).replace("ACCENT_COLOR", ac[0]).replace("ACCENT_HOVER", ac[1])
            .replace("ACCENT_LIGHT", ac[2]).replace("ACCENT_MUTED", ac[3]).replace("NAV_DOTS", dots)
            .replace('<html lang="en">', f'<html lang="{outline["course"]["lang"]}">')
            .replace('<link rel="stylesheet" href="styles.css">',
                     '<link rel="stylesheet" href="styles.css">\n  <link rel="stylesheet" href="course-extras.css">'))
    if has_math:  # KaTeX from the CDN (like the Google Fonts the base page already uses); offline -> raw TeX shown
        (course_dir / "course-math.js").write_text(MATH_JS, encoding="utf-8")
        base = base.replace(
            '<link rel="stylesheet" href="course-extras.css">',
            f'<link rel="stylesheet" href="course-extras.css">\n  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{KATEX}/dist/katex.min.css">')
        base = base.replace(
            '<script src="main.js" defer></script>',
            f'<script src="main.js" defer></script>\n  <script src="https://cdn.jsdelivr.net/npm/katex@{KATEX}/dist/katex.min.js" defer></script>'
            '\n  <script src="course-math.js" defer></script>')
    elif (course_dir / "course-math.js").exists():
        (course_dir / "course-math.js").unlink()
    (course_dir / "_base.html").write_text(base, encoding="utf-8")


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
    titles = [(i + 1, m["title"]) for i, (m, _) in enumerate(plan)] + [(n_mod + 1, L["glossary"])]
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
        bg = "var(--color-bg)" if i % 2 else "var(--color-bg-warm)"
        body = "\n".join(render_lesson(spec, les, ts, lang, src, segs) for spec, les in ls)
        sec = (f'<section class="module" id="module-{i}" style="background: {bg}">\n  <div class="module-content">\n'
               f'    <header class="module-header animate-in"><span class="module-number">{i:02d}</span>'
               f'<h1 class="module-title">{esc(m["title"])}</h1><p class="module-subtitle">{esc(m["subtitle"])}</p></header>\n'
               f'    <div class="module-body">\n{body}\n    </div>\n  </div>\n</section>\n')
        files[f"{i:02d}-{slugify(m['title'])}.html"] = sec
    scope = manifest["scope"]
    title = scope.get("title") or manifest["videos"][0]["title"]
    items = "".join(f'<dt>{esc(t)}{cite_chip(c[:1], lang, yt)}</dt><dd>{esc(d)}</dd>'
                    for _, (t, d, c, yt) in sorted(all_terms.items(), key=lambda kv: kv[0]))
    bg = "var(--color-bg)" if (n_mod + 1) % 2 else "var(--color-bg-warm)"
    files["99-glossary.html"] = (
        f'<section class="module" id="module-{n_mod + 1}" style="background: {bg}">\n  <div class="module-content">\n'
        f'    <header class="module-header animate-in"><span class="module-number">{n_mod + 1:02d}</span>'
        f'<h1 class="module-title">{L["glossary"]}</h1><p class="module-subtitle">{L["glossary_sub"]}</p></header>\n'
        f'    <div class="module-body"><section class="screen animate-in"><dl class="glossary-list">{items}</dl>'
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
    init_course(work, course_dir, {"course": outline["course"], "accent": outline.get("accent", "teal")}, titles, has_math=has_math, toc_html=toc_html)
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
