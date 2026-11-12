"""Stage 8 — render validated lesson drafts into the codebase-to-course HTML layout.

course/  styles.css main.js book-extras.css _base.html _footer.html build.sh  modules/NN-slug.html  index.html
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
           "from_book": "FROM THE BOOK", "plain": "IN PLAIN WORDS", "takeaways": "Key takeaways", "quiz": "Check yourself",
           "check": "Check Answers", "retry": "Try Again", "sources": "Sources", "glossary": "Glossary",
           "glossary_sub": "Every term explained in the course, with the book page it comes from.",
           "pages": "pp.", "page": "p.", "derived": "derived here, not printed in the book", "task": "Task", "hint": "Hint", "line": "Line", "from_book_fig": "From the book", "diagram": "Illustration made for this course", "symbols": "Symbols", "method": "Built from {title}, PDF pages {a}–{b}. Page references (p.N) are PDF page numbers."},
    "ru": {"objectives": "После этого урока вы сможете:", "why": "Зачем это нужно?", "metaphor": "Представьте так",
           "from_book": "ИЗ КНИГИ", "plain": "ПРОСТЫМИ СЛОВАМИ", "takeaways": "Главное", "quiz": "Проверьте себя",
           "check": "Проверить ответы", "retry": "Ещё раз", "sources": "Источники", "glossary": "Глоссарий",
           "glossary_sub": "Все термины курса со страницей книги, откуда они взяты.",
           "pages": "стр.", "page": "стр.", "derived": "выведено здесь, в книге этой формулы нет", "task": "Задача", "hint": "Подсказка", "line": "Строка", "from_book_fig": "Из книги", "diagram": "Иллюстрация для этого курса", "symbols": "Обозначения", "method": "Курс построен по книге «{title}», страницы PDF {a}–{b}. Ссылки (стр. N) — номера страниц PDF."},
}

EXTRA_CSS = diagrams.CSS + """/* book-to-course additions. Only adds classes that codebase-to-course does not have. */
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


def cite_chip(pages: list[int], lang: str) -> str:
    ps = sorted(set(pages))
    if not ps:
        return ""
    runs, start, prev = [], ps[0], ps[0]
    for p in ps[1:]:
        if p == prev + 1:
            prev = p
            continue
        runs.append((start, prev))
        start = prev = p
    runs.append((start, prev))
    label = ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in runs)
    t = L10N[lang]["pages" if len(ps) > 1 else "page"]
    return f'<span class="src-ref" title="PDF page {esc(label)}">{t}{esc(label)}</span>'


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


def _block(b: dict, ts: TermState, lang: str, book: str, idx: int) -> str:
    L = L10N[lang]
    t = b["type"]
    if t == "text":
        return f'<p>{ts.markup(b["text"])}{cite_chip(b["cite"], lang)}</p>'
    if t == "cards":
        cards = []
        for i, it in enumerate(b["items"]):
            icon = f'<div class="pattern-icon" style="background: var(--color-actor-{i % 5 + 1})">{esc(it.get("icon", "•"))}</div>' if it.get("icon") else ""
            cards.append(f'<div class="pattern-card" style="border-top: 3px solid var(--color-actor-{i % 5 + 1})">{icon}'
                         f'<h4 class="pattern-title">{ts.markup(it["title"])}</h4>'
                         f'<p class="pattern-desc">{ts.markup(it["text"])}</p></div>')
        return f'<div class="pattern-cards stagger-children">{"".join(cards)}</div>{_cite_line(b["cite"], lang)}'
    if t == "steps":
        steps = "".join(
            f'<div class="step-card"><div class="step-num">{i + 1}</div><div class="step-body">'
            f'<strong>{ts.markup(it["title"])}</strong><p>{ts.markup(it["text"])}</p></div></div>'
            for i, it in enumerate(b["items"]))
        return f'<div class="step-cards">{steps}</div>{_cite_line(b["cite"], lang)}'
    if t == "quote":
        return (f'<div class="translation-block quote animate-in"><div class="translation-code">'
                f'<span class="translation-label">{L["from_book"]}</span>'
                f'<div class="quote-body">«{plain_markup(b.get("shown") or b["text"]) if b.get("shown") else esc(b["text"])}»</div>'
                f'<span class="quote-attrib">— {esc(book)}, {L["page"]}{b["page"]}</span></div>'
                f'<div class="translation-english"><span class="translation-label">{L["plain"]}</span>'
                f'<div class="translation-lines"><p class="tl">{ts.markup(b["meaning"])}</p></div></div></div>')
    if t == "figure":
        alt = esc(b.get("alt") or b["caption"])
        return (f'<figure class="book-figure animate-in"><img src="figures/{esc(b["fig"])}.png" alt="{alt}" loading="lazy">'
                f'<figcaption><span class="fig-tag">{L["from_book_fig"]}</span>{ts.markup(b["caption"])}{cite_chip([b["page"]], lang)}</figcaption></figure>')
    if t == "diagram":
        svg = diagrams.render_svg(b, f"d{next(ts.uid)}")
        return (f'<figure class="diagram animate-in"><p class="fig-title">{esc(b["title"])}</p>{svg}'
                f'<figcaption><span class="fig-tag">{L["diagram"]}</span>{ts.markup(b["caption"])}{cite_chip(b["cite"], lang)}</figcaption></figure>')
    if t == "code":
        code = b["code"].strip("\n")
        pre = "\n".join(f'<span class="code-line">{esc(ln) or " "}</span>' for ln in code.split("\n"))
        rows = "".join(f'<p class="tl"><span class="tl-at">{L["line"]} {esc(str(x["at"]).replace("-", "–"))}</span> {ts.markup(x["text"])}</p>' for x in b["lines"])
        note = f'<p class="code-note">{ts.markup(b["note"])}</p>' if b.get("note") else ""
        return (f'<div class="translation-block animate-in"><div class="translation-code"><span class="translation-label">{esc(b["lang"]).upper()} · '
                f'{L["page"]}{b["page"]}</span><pre><code>{pre}</code></pre></div>'
                f'<div class="translation-english"><span class="translation-label">{L["plain"]}</span><div class="translation-lines">{rows}</div></div></div>{note}')
    if t == "task":
        hint = f'<details><summary>{L["hint"]}</summary><p>{ts.markup(b["hint"])}</p></details>' if b.get("hint") else ""
        return (f'<div class="task-card animate-in"><span class="task-label">{L["task"]} · {L["page"]}{b["page"]}</span>'
                f'<p class="task-statement">{plain_markup(b["shown"]) if b.get("shown") else esc(b["statement"])}</p>'
                f'<p><strong>{L["plain"].capitalize()}:</strong> {ts.markup(b["plain"])}</p>{hint}</div>')
    if t == "math":
        sym = "".join(f'<dt>{_math_span(sy["sym"])}</dt><dd>{ts.markup(sy["meaning"])}</dd>' for sy in b["symbols"])
        cap = f'<figcaption>{ts.markup(b["caption"])}</figcaption>' if b.get("caption") else ""
        badge = f'<span class="origin-badge">{L["derived"]}</span>' if b["origin"] == "derived" else ""
        return (f'<figure class="math-block animate-in"><div class="math-eq">{_math_span(b["latex"], display=True)}</div>{cap}'
                f'<dl class="symbol-list" aria-label="{L["symbols"]}">{sym}</dl>'
                f'<p class="math-meta">{badge}{cite_chip(b["cite"], lang)}</p></figure>')
    if t == "callout":
        v = b["variant"]
        return (f'<div class="callout callout-{v}"><div class="callout-icon">{ICONS[v]}</div><div class="callout-content">'
                f'<strong class="callout-title">{ts.markup(b["title"])}</strong>'
                f'<p>{ts.markup(b["text"])}{cite_chip(b["cite"], lang)}</p></div></div>')
    raise ValueError(f"unknown block type {t}")


def _cite_line(pages: list[int], lang: str) -> str:
    chip = cite_chip(pages, lang)
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
            f'data-explanation-right="{esc(plain_markup(q["explain_right"]))} ({L["page"]}{", ".join(map(str, sorted(set(q["cite"]))))})" '
            f'data-explanation-wrong="{esc(plain_markup(q["explain_wrong"]))}">'
            f'<h3 class="quiz-question">{plain_markup(q["question"])}</h3><div class="quiz-options">{opts}</div>'
            f'<div class="quiz-feedback"></div></div>')
    return (f'<div class="quiz-container" id="{qid}">{"".join(blocks)}'
            f'<button class="quiz-check-btn" onclick="checkQuiz(\'{qid}\')">{L["check"]}</button>'
            f'<button class="quiz-reset-btn" onclick="resetQuiz(\'{qid}\')">{L["retry"]}</button></div>')


def render_lesson(spec: dict, les: dict, ts: TermState, lang: str, book: str, chap: dict) -> str:
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
        body = "\n".join(_block(b, ts, lang, book, i) for i, b in enumerate(s["blocks"]))
        out.append(f'<section class="screen animate-in"><h2 class="screen-heading">{ts.markup(s["heading"])}</h2>\n{body}</section>')
    take = "".join(
        f'<div class="step-card"><div class="step-num">{i + 1}</div><div class="step-body"><p>{ts.markup(t)}</p></div></div>'
        for i, t in enumerate(les["key_takeaways"]))
    srcs = ", ".join(f"{c} ({L['pages']}{chap[c]['page_start']}–{chap[c]['page_end']})" for c in les["sources"]["chapters"] if c in chap)
    out.append(
        f'<section class="screen animate-in"><h2 class="screen-heading">{L["takeaways"]}</h2>'
        f'<div class="step-cards">{take}</div>'
        f'<h2 class="screen-heading" style="margin-top:3rem">{L["quiz"]}</h2>{_quiz(les, lang)}'
        f'<p class="method-note">{L["sources"]}: {esc(srcs)}</p></section>')
    return "\n".join(out)


KATEX = "0.16.11"
MATH_JS = (ASSETS / "book-math.js").read_text(encoding="utf-8")


def init_course(work: Work, course_dir: Path, outline: dict, module_titles: list[tuple[int, str]],
                has_math: bool = False, toc_html: str = "") -> None:
    course_dir.mkdir(parents=True, exist_ok=True)
    (course_dir / "modules").mkdir(exist_ok=True)
    for f in ("styles.css", "main.js", "_footer.html", "build.sh"):
        shutil.copyfile(ASSETS / f, course_dir / f)
    accent_name = outline.get("accent", "teal")
    (course_dir / "book-extras.css").write_text(EXTRA_CSS + ui.ui_css(accent_name, ACCENTS[accent_name]), encoding="utf-8")
    (course_dir / "book-ui.js").write_text(ui.UI_JS, encoding="utf-8")
    base = (ASSETS / "_base.html").read_text(encoding="utf-8")
    title = outline["book"].get("course_title") or outline["book"]["title"]
    ac = ACCENTS[accent_name]
    ac = (ui.ensure_white_contrast(ac[0]), ui.ensure_white_contrast(ac[1], 5.2), ac[2], ac[3])   # white text on accent fills must reach WCAG AA
    lang = outline["book"]["lang"]
    # chrome: Home + Contents buttons, theme toggle, skip link, contents drawer, no-flash theme script, no-JS fallback
    base = base.replace('<span class="nav-title">COURSE_TITLE</span>', ui.nav_left(lang, title))
    base = re.sub(r"NAV_DOTS\s*</div>", lambda m: "NAV_DOTS\n      </div>\n      " + ui.nav_actions(lang), base, count=1)
    base = base.replace("</nav>", "</nav>\n" + toc_html, 1)
    base = base.replace("<body>", f'<body>\n  <a class="skip-link" href="#main">{ui.TEXT[lang]["skip"]}</a>', 1)
    base = base.replace('<meta name="viewport" content="width=device-width, initial-scale=1.0">',
                        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <meta name="color-scheme" content="light dark">\n  '
                        + ui.INLINE_THEME_JS, 1)
    base = base.replace("</head>", "  <noscript><style>.animate-in{opacity:1;transform:none}</style></noscript>\n</head>", 1)
    base = base.replace('<script src="main.js" defer></script>', '<script src="main.js" defer></script>\n  <script src="book-ui.js" defer></script>', 1)
    base = re.sub(r"<!--\s*One <button> per module.*?-->\s*", "", base, flags=re.S)   # template instructions, not for the output
    base = base.replace('role="tablist"', 'role="group" aria-label="' + ("Modules" if lang == "en" else "Модули") + '"')
    dots = "\n        ".join(
        f'<button class="nav-dot" data-target="module-{n}" data-tooltip="{esc(t)}" aria-label="Module {n}: {esc(t)}"></button>'
        for n, t in module_titles)
    base = (base.replace("COURSE_TITLE", esc(title)).replace("ACCENT_COLOR", ac[0]).replace("ACCENT_HOVER", ac[1])
            .replace("ACCENT_LIGHT", ac[2]).replace("ACCENT_MUTED", ac[3]).replace("NAV_DOTS", dots)
            .replace('<html lang="en">', f'<html lang="{outline["book"]["lang"]}">')
            .replace('<link rel="stylesheet" href="styles.css">',
                     '<link rel="stylesheet" href="styles.css">\n  <link rel="stylesheet" href="book-extras.css">'))
    if has_math:  # KaTeX from the CDN (like the Google Fonts the base page already uses); offline -> raw TeX shown
        (course_dir / "book-math.js").write_text(MATH_JS, encoding="utf-8")
        base = base.replace(
            '<link rel="stylesheet" href="book-extras.css">',
            f'<link rel="stylesheet" href="book-extras.css">\n  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{KATEX}/dist/katex.min.css">')
        base = base.replace(
            '<script src="main.js" defer></script>',
            f'<script src="main.js" defer></script>\n  <script src="https://cdn.jsdelivr.net/npm/katex@{KATEX}/dist/katex.min.js" defer></script>'
            '\n  <script src="book-math.js" defer></script>')
    elif (course_dir / "book-math.js").exists():
        (course_dir / "book-math.js").unlink()
    (course_dir / "_base.html").write_text(base, encoding="utf-8")


def render(work: Work, course_dir: Path, partial: bool = False) -> dict:
    outline, manifest = read_json(work.outline), read_json(work.manifest)
    lang = outline["book"]["lang"]
    book = outline["book"]["title"]
    chap = {c["id"]: c for c in manifest["chapters"]}
    missing = [l["id"] for m in outline["modules"] for l in m["lessons"] if not (work.drafts / f"{l['id']}.json").exists()]
    if missing and not partial:
        raise SystemExit(f"missing drafts: {', '.join(missing)} (write them, or pass --partial)")
    plan = []
    for m in outline["modules"]:
        ls = [(l, read_json(work.drafts / f"{l['id']}.json")) for l in m["lessons"] if (work.drafts / f"{l['id']}.json").exists()]
        if ls:
            plan.append((m, ls))
    n_mod = len(plan)
    titles = [(i + 1, m["title"]) for i, (m, _) in enumerate(plan)] + [(n_mod + 1, L10N[lang]["glossary"])]
    files: dict[str, str] = {}
    uid = itertools.count(1)  # deterministic ids for SVG markers/clip paths
    figs = sorted({b["fig"] for _, ls in plan for _, les in ls for s in les["screens"] for b in s["blocks"] if b["type"] == "figure"})
    all_terms: dict[str, tuple[str, str, list[int]]] = {}
    for i, (m, ls) in enumerate(plan, start=1):
        gl: dict[str, str] = {}
        for _, les in ls:
            for g in les["glossary"]:
                gl.setdefault(g["term"].strip().lower(), g["definition"])
                all_terms.setdefault(g["term"].strip().lower(), (g["term"], g["definition"], g["cite"]))
        ts = TermState(gl, uid)
        bg = "var(--color-bg)" if i % 2 else "var(--color-bg-warm)"
        body = "\n".join(render_lesson(spec, les, ts, lang, book, chap) for spec, les in ls)
        sec = (f'<section class="module" id="module-{i}" style="background: {bg}">\n  <div class="module-content">\n'
               f'    <header class="module-header animate-in"><span class="module-number">{i:02d}</span>'
               f'<h1 class="module-title">{esc(m["title"])}</h1><p class="module-subtitle">{esc(m["subtitle"])}</p></header>\n'
               f'    <div class="module-body">\n{body}\n    </div>\n  </div>\n</section>\n')
        files[f"{i:02d}-{slugify(m['title'])}.html"] = sec
    L = L10N[lang]
    a, b = manifest["scope"]["pages"]
    items = "".join(
        f'<dt>{esc(t)}{cite_chip(c, lang)}</dt><dd>{esc(d)}</dd>'
        for _, (t, d, c) in sorted(all_terms.items(), key=lambda kv: kv[0]))
    bg = "var(--color-bg)" if (n_mod + 1) % 2 else "var(--color-bg-warm)"
    gl_html = (f'<section class="module" id="module-{n_mod + 1}" style="background: {bg}">\n  <div class="module-content">\n'
               f'    <header class="module-header animate-in"><span class="module-number">{n_mod + 1:02d}</span>'
               f'<h1 class="module-title">{L["glossary"]}</h1><p class="module-subtitle">{L["glossary_sub"]}</p></header>\n'
               f'    <div class="module-body"><section class="screen animate-in"><dl class="glossary-list">{items}</dl>'
               f'<p class="method-note">{esc(L["method"].format(title=book, a=a, b=b))}</p></section></div>\n  </div>\n</section>\n')
    files["99-glossary.html"] = gl_html
    course_title = outline["book"].get("course_title") or outline["book"]["title"]
    mods = [{"n": i, "title": m["title"], "subtitle": m["subtitle"],
             "lessons": [{"id": spec["id"].lower(), "title": les["title"]} for spec, les in ls]} for i, (m, ls) in enumerate(plan, start=1)]
    stats = {"lessons": sum(len(m["lessons"]) for m in mods), "quiz": sum(len(les["quiz"]) for _, ls in plan for _, les in ls), "terms": len(all_terms)}
    files["00-cover.html"] = ui.build_cover(lang, course_title, book, (a, b), mods, stats)
    toc_html = ui.build_toc(lang, course_title, mods, len(all_terms))
    has_math = any('class="tex"' in h for h in files.values())
    init_course(work, course_dir, outline, titles, has_math=has_math, toc_html=toc_html)
    for old in (course_dir / "modules").glob("*.html"):
        old.unlink()
    for name, h in files.items():
        (course_dir / "modules" / name).write_text(h, encoding="utf-8")
    if figs:
        from pathlib import Path

        from .figtools import crop_fig, find_fig
        fdir = course_dir / "figures"
        fdir.mkdir(exist_ok=True)
        for fid in figs:
            if not crop_fig(Path(manifest["book"]["pdf"]), find_fig(work, fid), fdir / f"{fid}.png"):
                raise SystemExit(f"cannot crop {fid}; fix the lesson (see `b2c.py validate`)")
    assemble(course_dir)
    return {"modules": n_mod, "lessons": sum(len(ls) for _, ls in plan), "glossary_terms": len(all_terms), "math": has_math, "figures": len(figs),
            "index": str(course_dir / "index.html")}


def assemble(course_dir: Path) -> None:
    parts = [(course_dir / "_base.html").read_text(encoding="utf-8")]
    parts += [p.read_text(encoding="utf-8") for p in sorted((course_dir / "modules").glob("*.html"))]
    parts.append((course_dir / "_footer.html").read_text(encoding="utf-8"))
    (course_dir / "index.html").write_text("".join(parts), encoding="utf-8")
