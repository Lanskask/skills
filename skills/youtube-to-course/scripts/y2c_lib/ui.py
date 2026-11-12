"""Course chrome: theme colours, page shell (top bar, contents drawer, cover), builders for their markup.

Design decisions (see DECISIONS.md):
  * Theme = tokens in assets/course.css; the dark theme only overrides them. Default follows the system (`prefers-color-scheme`);
    the toggle stores an explicit choice in localStorage (wrapped in try/catch) and an inline script in <head> applies it before
    first paint (no flash). Toggling back to the system's theme returns to "auto".
  * One per-course colour, the "pen" (links, marks, buttons). Each pen has a light and a dark value; both are checked for contrast
    against the paper in tests, so a new pen cannot ship unreadable.
  * Contents = drawer on narrow screens (focus moves in, Tab trapped, Esc closes, page behind inert), docked on wide screens.
  * Home = a cover section (#home, not a .module) with the module list and a Start button.
"""
from __future__ import annotations

import html
from pathlib import Path

# (pen on the light paper, pen on the dark paper); light: white text on it reaches 4.5:1, dark: dark text on it does
PENS = {
    "indigo": ("#1F3A93", "#9DB4FF"),
    "vermillion": ("#B33A1D", "#F59478"),
    "coral": ("#B04434", "#F5A394"),
    "teal": ("#1B6A8A", "#7CC4E0"),
    "amber": ("#8A5F00", "#E8C268"),
    "forest": ("#1F6B3F", "#74CC98"),
}
DEFAULT_PEN = "indigo"


def _lum(h: str) -> float:
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two #RRGGBB colours."""
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def pen_css(name: str) -> str:
    light, dark = PENS[name]
    return (f":root {{ --pen: {light}; }}\n:root[data-theme=\"dark\"] {{ --pen: {dark}; }}\n"
            f"@media (prefers-color-scheme: dark) {{ :root:not([data-theme=\"light\"]) {{ --pen: {dark}; }} }}")


ASSETS = Path(__file__).resolve().parents[2] / "assets"

INLINE_THEME_JS = ("<script>try{var t=localStorage.getItem('b2c-theme');if(t==='dark'||t==='light')"
                   "document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>")

UI_JS = (ASSETS / "course-ui.js").read_text(encoding="utf-8")

# ── markup builders ──────────────────────────────────────────────────────

ICONS = {
    "home": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9.5h4.5v-5h4v5h4.5V10"/></svg>',
    "menu": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6.5h16M4 12h16M4 17.5h10"/></svg>',
    "moon": '<svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>',
    "sun": ('<svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
            '<path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/></svg>'),
    "close": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
}

TEXT = {
    "en": {"home": "Home", "contents": "Contents", "dark": "Dark theme", "close": "Close contents", "skip": "Skip to content", "start": "Start learning",
           "read": "read", "kicker": "Interactive course", "from": "Built from “{title}” ({a})", "module": "module", "modules": "modules",
           "lesson": "lesson", "lessons": "lessons", "quiz": "quiz question", "quizzes": "quiz questions", "terms": "glossary terms", "term": "glossary term",
           "hint": "Tip: <b>Contents</b> jumps to any lesson, the margin shows timestamps and definitions, and the moon/sun button switches the theme "
                   "(it follows your system until you choose).", "toc_nav": "Table of contents", "glossary": "Glossary"},
    "ru": {"home": "Главная", "contents": "Оглавление", "dark": "Тёмная тема", "close": "Закрыть оглавление", "skip": "К содержимому", "start": "Начать",
           "read": "прочитано", "kicker": "Интерактивный курс", "from": "Построен по видео «{title}» ({a})", "module": "модуль", "modules": "модулей",
           "lesson": "урок", "lessons": "уроков", "quiz": "вопрос", "quizzes": "вопросов", "terms": "терминов", "term": "термин",
           "hint": "Подсказка: <kbd>↑</kbd> <kbd>↓</kbd> — между модулями, <b>Оглавление</b> — к любому уроку, кнопка луны/солнца переключает тему "
                   "(по умолчанию — как в системе).", "toc_nav": "Оглавление", "glossary": "Глоссарий"},
}


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def nav_left(lang: str, course_title: str) -> str:
    t = TEXT[lang]
    return (f'<div class="nav-left"><a class="nav-btn" id="nav-home" href="#home" aria-label="{t["home"]}">{ICONS["home"]}'
            f'<span class="nav-btn-label">{t["home"]}</span></a>'
            f'<button type="button" class="nav-btn" data-toc-open aria-controls="toc" aria-expanded="false" aria-label="{t["contents"]}">{ICONS["menu"]}'
            f'<span class="nav-btn-label">{t["contents"]}</span></button>'
            f'<span class="nav-title">{_e(course_title)}</span></div>')


def nav_actions(lang: str) -> str:
    t = TEXT[lang]
    return (f'<div class="nav-actions"><button type="button" class="nav-btn theme-toggle" id="theme-toggle" aria-pressed="false" '
            f'aria-label="{t["dark"]}" title="{t["dark"]}">{ICONS["moon"]}{ICONS["sun"]}</button></div>')


def build_toc(lang: str, course_title: str, modules: list[dict], glossary_n: int) -> str:
    """modules: [{"n": 1, "title": ..., "lessons": [{"id": "l-01", "title": ...}]}]; glossary module number = len(modules)+1."""
    t = TEXT[lang]
    items = []
    for m in modules:
        lessons = "".join(f'<li><a href="#{_e(l["id"])}" data-spy="{_e(l["id"])}">{_e(l["title"])}</a></li>' for l in m["lessons"])
        items.append(f'<li class="toc-module"><a href="#module-{m["n"]}" data-spy="module-{m["n"]}"><span class="toc-num">{m["n"]:02d}</span>{_e(m["title"])}</a>'
                     f'<ol>{lessons}</ol></li>')
    g = len(modules) + 1
    items.append(f'<li class="toc-module"><a href="#module-{g}" data-spy="module-{g}"><span class="toc-num">{g:02d}</span>{t["glossary"]}</a></li>')
    return (f'<div class="toc-backdrop" id="toc-backdrop"></div>'
            f'<nav class="toc" id="toc" aria-label="{t["toc_nav"]}" tabindex="-1">'
            f'<div class="toc-head"><p class="toc-title">{_e(course_title)}</p>'
            f'<button type="button" class="nav-btn toc-close" data-toc-close aria-label="{t["close"]}">{ICONS["close"]}</button></div>'
            f'<div class="toc-meter"><div class="toc-meter-track" aria-hidden="true"><span class="toc-meter-bar" id="toc-progress-bar"></span></div>'
            f'<p class="toc-pct"><span id="toc-pct">0%</span> {t["read"]}</p></div>'
            f'<div class="toc-scroll"><ol class="toc-list">{"".join(items)}</ol></div></nav>')


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def build_cover(lang: str, course_title: str, book_title: str, pages: tuple[int, int], modules: list[dict], stats: dict) -> str:
    t = TEXT[lang]
    cards = "".join(
        f'<li><a class="cover-card" href="#module-{m["n"]}" data-go="module-{m["n"]}"><span class="cm-num">{m["n"]:02d}</span>'
        f'<span class="cm-title">{_e(m["title"])}</span><span class="cm-sub">{_e(m["subtitle"])}</span>'
        f'<span class="cm-meta">{len(m["lessons"])} {_plural(len(m["lessons"]), t["lesson"], t["lessons"])}</span></a></li>' for m in modules)
    s = [(len(modules), _plural(len(modules), t["module"], t["modules"])), (stats["lessons"], _plural(stats["lessons"], t["lesson"], t["lessons"])),
         (stats["quiz"], _plural(stats["quiz"], t["quiz"], t["quizzes"])), (stats["terms"], _plural(stats["terms"], t["term"], t["terms"]))]
    stat_html = "".join(f"<li><strong>{n}</strong>{_e(label)}</li>" for n, label in s if n)
    return (f'<section class="cover" id="home" aria-labelledby="cover-title"><div class="cover-inner">'
            f'<p class="cover-kicker">{t["kicker"]}</p><h1 id="cover-title">{_e(course_title)}</h1>'
            f'<p class="cover-lead">{_e(t["from"].format(title=book_title, a=pages[0], b=pages[1]))}</p>'
            f'<ul class="cover-stats">{stat_html}</ul>'
            f'<div class="cover-actions"><a class="btn btn-primary" href="#module-1" data-go="module-1">{t["start"]}</a>'
            f'<button type="button" class="btn" data-toc-open aria-controls="toc" aria-expanded="false">{t["contents"]}</button></div>'
            f'<ol class="cover-modules">{cards}</ol><p class="cover-hint">{t["hint"]}</p></div></section>\n')


def base_html(lang: str, title: str, accent: str, toc_html: str, has_math: bool, katex: str, font_links: str) -> str:
    """Everything before the first module: head, skip link, top bar, contents drawer, opening <main>."""
    t = TEXT[lang]
    math_css = f'\n  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{katex}/dist/katex.min.css">' if has_math else ""
    math_js = (f'\n  <script src="https://cdn.jsdelivr.net/npm/katex@{katex}/dist/katex.min.js" defer></script>'
               '\n  <script src="course-math.js" defer></script>') if has_math else ""
    return (f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n  <meta charset="UTF-8">\n'
            f'  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <meta name="color-scheme" content="light dark">\n'
            f"  {INLINE_THEME_JS}\n  <title>{_e(title)}</title>\n  {font_links}\n"
            f'  <link rel="stylesheet" href="course.css">\n  <style>{pen_css(accent)}</style>{math_css}\n'
            f'  <noscript><style>.toc{{position:static;transform:none;visibility:visible;width:auto;box-shadow:none}}.toc-close,[data-toc-open],.theme-toggle{{display:none}}main{{padding-left:0!important}}</style></noscript>\n  <script src="course-ui.js" defer></script>{math_js}\n</head>\n<body>\n'
            f'  <a class="skip-link" href="#main">{t["skip"]}</a>\n'
            f'  <header class="bar" id="nav">{nav_left(lang, title)}<p class="bar-where" id="bar-where"></p>{nav_actions(lang)}'
            f'<span class="bar-progress" id="bar-progress" aria-hidden="true"></span></header>\n{toc_html}\n  <main id="main">\n')


FOOTER = "  </main>\n</body>\n</html>\n"
