"""Course chrome: dark/light theme, table-of-contents drawer, Home button, cover page, focus/keyboard/motion/print rules.

Design decisions (see DECISIONS.md):
  * Theme = tokens. styles.css (copied verbatim from codebase-to-course) already uses CSS variables, so the dark theme only overrides them.
    Default follows the system (`prefers-color-scheme`); the toggle stores an explicit choice in localStorage (wrapped in try/catch) and an
    inline script in <head> applies it before first paint (no flash). Toggling back to the system's theme returns to "auto".
  * The toggle is a button with aria-pressed and a constant label ("Dark theme"), not a label that flips.
  * Accent colour is used as a background (white text on it) AND as text; no single value passes contrast for both on a dark page, so there is a
    separate --color-accent-text (darker on light, lighter on dark).
  * TOC = slide-over drawer (same pattern on desktop and phones): focus moves in, Tab is trapped, Esc / backdrop / link click close it, focus returns,
    the page behind is inert, hidden state uses visibility so closed links leave the tab order. Scroll-spy marks the current lesson (aria-current).
  * Home = a cover section (#home, deliberately NOT a .module: main.js indexes .module elements) with module cards and a Start button.
  * Skip link, :focus-visible rings, 40px targets, reduced-motion and print rules, no-JS fallback for the reveal animations.
"""
from __future__ import annotations

import html
from pathlib import Path

# ── colour tokens ────────────────────────────────────────────────────────

# (light-theme accent text, dark-theme accent text, dark-theme accent used as a fill: white text must stay readable on it)
ACCENT_TEXT = {
    "vermillion": ("#B93C20", "#F28B71", "#D94F30"),
    "coral": ("#B34B39", "#F4A08F", "#C85A47"),
    "teal": ("#1F6280", "#78C4E0", "#2A7B9B"),
    "amber": ("#8A6A12", "#E9C46A", "#9A7416"),
    "forest": ("#226B41", "#6CCB95", "#2D8B55"),
}
DARK = {
    "--color-bg": "#1B1916", "--color-bg-warm": "#221F1B", "--color-bg-code": "#0F0F17",
    "--color-text": "#EDE8E0", "--color-text-secondary": "#B8B0A5", "--color-text-muted": "#8C847A",
    "--color-border": "#3B3631", "--color-border-light": "#2D2925", "--color-surface": "#26231F", "--color-surface-warm": "#2B2723",
    "--color-success": "#5CBF86", "--color-error": "#EF7B7B", "--color-info": "#6BB8D6",
    "--color-actor-1": "#EE6B4C", "--color-actor-2": "#5AB0CF", "--color-actor-3": "#A99DD6", "--color-actor-4": "#E5C064", "--color-actor-5": "#5BBE88",
    "--shadow-sm": "0 1px 2px rgba(0,0,0,.35)", "--shadow-md": "0 4px 12px rgba(0,0,0,.40)",
    "--shadow-lg": "0 8px 24px rgba(0,0,0,.45)", "--shadow-xl": "0 16px 48px rgba(0,0,0,.50)",
}


def _lum(h: str) -> float:
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two #RRGGBB colours."""
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def ensure_white_contrast(fill: str, target: float = 4.6) -> str:
    """Darken `fill` in small steps until white text on it reaches `target`:1 (WCAG AA for normal text is 4.5)."""
    for _ in range(40):
        if contrast("#FFFFFF", fill) >= target:
            break
        fill = _mix(fill, "#000000", 0.96)
    return fill


def _mix(a: str, b: str, t: float) -> str:
    """Blend hex colour a into b by t (0..1)."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02X}" for x, y in zip(pa, pb))


def dark_tokens(accent: str, light_accent: tuple[str, str, str, str]) -> dict[str, str]:
    surf = DARK["--color-surface"]
    t = dict(DARK)
    fill = ensure_white_contrast(ACCENT_TEXT[accent][2])
    t["--color-accent"] = fill
    t["--color-accent-hover"] = _mix(fill, "#FFFFFF", 0.85)
    t["--color-accent-light"] = _mix(fill, surf, 0.20)
    t["--color-accent-muted"] = _mix(ACCENT_TEXT[accent][1], DARK["--color-bg"], 0.65)
    t["--color-accent-text"] = ACCENT_TEXT[accent][1]
    t["--color-success-light"] = _mix(DARK["--color-success"], surf, 0.16)
    t["--color-error-light"] = _mix(DARK["--color-error"], surf, 0.16)
    t["--color-info-light"] = _mix(DARK["--color-info"], surf, 0.16)
    return t


def ui_css(accent: str, light_accent: tuple[str, str, str, str]) -> str:
    dk = dark_tokens(accent, light_accent)
    body = "".join(f"  {k}: {v};\n" for k, v in dk.items())
    return f""":root {{ color-scheme: light; --color-accent-text: {ACCENT_TEXT[accent][0]}; }}
:root[data-theme="dark"] {{ color-scheme: dark;
{body}}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ color-scheme: dark;
{body}  }}
}}
""" + UI_CSS


UI_CSS = """
/* ── course chrome (book-to-course) ─────────────────────────── */
html { -webkit-text-size-adjust: 100%; }
body { text-rendering: optimizeLegibility; transition: background-color .25s ease, color .25s ease; }
.nav { background: color-mix(in srgb, var(--color-bg) 90%, transparent); }
.screen p, .screen li { max-width: 70ch; }
.screen p { line-height: 1.7; }
[id] { scroll-margin-top: calc(var(--nav-height) + 12px); }
:where(a, button, summary, [tabindex]):focus-visible { outline: 3px solid var(--color-accent-text); outline-offset: 2px; border-radius: 4px; }
.term:hover, .term.active, .btn:hover { color: var(--color-accent-text); }
.btn-primary:hover { color: #fff; }
.ft-folder > .ft-name { color: var(--color-accent-text); }
.book-figure img { background: #fff; padding: 6px; }

.skip-link { position: fixed; left: 12px; top: -64px; z-index: 3000; padding: .6rem 1rem; border-radius: var(--radius-sm);
  background: var(--color-accent); color: #fff; font-weight: 600; text-decoration: none; transition: top .15s; }
.skip-link:focus { top: 12px; }

.nav-inner { gap: var(--space-3); }
.nav-left { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
.nav-actions { display: flex; align-items: center; gap: var(--space-2); }
.nav-btn { display: inline-flex; align-items: center; justify-content: center; gap: .45rem; min-width: 40px; height: 40px; padding: 0 .7rem;
  border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-text); font: inherit;
  font-size: var(--text-sm); font-weight: 500; line-height: 1; cursor: pointer; text-decoration: none;
  transition: background var(--duration-fast), border-color var(--duration-fast); }
.nav-btn:hover { background: var(--color-bg-warm); border-color: var(--color-border); }
.nav-btn[aria-expanded="true"], .nav-btn[aria-pressed="true"] { background: var(--color-accent-light); border-color: var(--color-accent-muted); }
.nav-btn svg { width: 20px; height: 20px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.theme-toggle .i-sun { display: none; }
.theme-toggle.is-dark .i-sun { display: inline; }
.theme-toggle.is-dark .i-moon { display: none; }
.nav-title { margin-left: var(--space-2); }
@media (max-width: 960px) { .nav-title { display: none; } }
@media (max-width: 720px) { .nav-dots { display: none; } .nav-btn .nav-btn-label { display: none; } .nav-inner { padding: 0 var(--space-3); } }

/* table of contents drawer */
.toc-backdrop { position: fixed; inset: 0; z-index: 1900; background: rgba(0,0,0,.45); opacity: 0; visibility: hidden;
  transition: opacity .25s ease, visibility 0s .25s; }
.toc-backdrop.open { opacity: 1; visibility: visible; transition: opacity .25s ease; }
.toc { position: fixed; top: 0; left: 0; bottom: 0; z-index: 2000; width: min(380px, 88vw); display: flex; flex-direction: column;
  background: var(--color-surface); color: var(--color-text); border-right: 1px solid var(--color-border); box-shadow: var(--shadow-xl);
  transform: translateX(-102%); visibility: hidden; transition: transform .3s var(--ease-out), visibility 0s .3s; overscroll-behavior: contain; }
.toc.open { transform: none; visibility: visible; transition: transform .3s var(--ease-out); }
.toc:focus { outline: none; }
.toc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3); padding: var(--space-5) var(--space-5) var(--space-3); }
.toc-title { font-family: var(--font-display); font-weight: 700; font-size: var(--text-lg); line-height: 1.25; margin: 0; }
.toc-meter { margin: 0 var(--space-5) var(--space-3); }
.toc-meter-track { height: 4px; border-radius: 999px; background: var(--color-border-light); overflow: hidden; }
.toc-meter-bar { display: block; height: 100%; width: 0; background: var(--color-accent); transition: width .2s linear; }
.toc-pct { margin: .35rem 0 0; font-size: var(--text-xs); color: var(--color-text-secondary); }
.toc-scroll { overflow-y: auto; padding: 0 var(--space-3) var(--space-8); flex: 1; }
.toc-list, .toc-list ol { list-style: none; margin: 0; padding: 0; }
.toc-list > li { margin-top: var(--space-1); }
.toc-list a { display: flex; gap: .6rem; align-items: baseline; padding: .55rem .75rem; border-radius: var(--radius-sm); color: var(--color-text);
  text-decoration: none; font-size: var(--text-sm); line-height: 1.35; min-height: 40px; }
.toc-list a:hover { background: var(--color-bg-warm); }
.toc-module > a { font-weight: 600; }
.toc-num { flex: none; font-family: var(--font-mono); font-size: var(--text-xs); color: var(--color-text-secondary); min-width: 1.6rem; }
.toc-list ol { margin: 0 0 var(--space-2) 2.1rem; border-left: 1px solid var(--color-border-light); }
.toc-list ol a { font-weight: 400; color: var(--color-text-secondary); padding-left: .9rem; }
.toc-list a[aria-current="location"] { background: var(--color-accent-light); color: var(--color-text); box-shadow: inset 3px 0 0 var(--color-accent); }
.toc-list a.is-read::after { content: "✓"; margin-left: auto; color: var(--color-accent-text); font-size: var(--text-xs); }
body.toc-open { overflow: hidden; }

/* cover / home */
.cover { min-height: 100vh; min-height: 100dvh; display: flex; align-items: center; padding: calc(var(--nav-height) + var(--space-12)) var(--space-6) var(--space-16);
  background: radial-gradient(ellipse at 15% 20%, var(--color-accent-light), transparent 55%), var(--color-bg); scroll-snap-align: start; }
.cover-inner { width: 100%; max-width: var(--content-width-wide); margin: 0 auto; }
.cover-kicker { margin: 0 0 var(--space-3); font-size: var(--text-sm); letter-spacing: .08em; text-transform: uppercase; color: var(--color-accent-text); font-weight: 600; }
.cover h1 { font-family: var(--font-display); font-size: clamp(2.1rem, 5.5vw, 3.75rem); line-height: 1.08; font-weight: 800; margin: 0 0 var(--space-4); max-width: 18ch; text-wrap: balance; }
.cover-lead { font-size: var(--text-lg); color: var(--color-text-secondary); max-width: 52ch; margin: 0 0 var(--space-6); }
.cover-stats { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-5); list-style: none; margin: 0 0 var(--space-8); padding: 0; color: var(--color-text-secondary); font-size: var(--text-sm); }
.cover-stats strong { color: var(--color-text); font-size: var(--text-xl); font-family: var(--font-display); margin-right: .25em; }
.cover-actions { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-bottom: var(--space-12); }
.cover .btn { display: inline-flex; align-items: center; min-height: 44px; padding: 0 1.4rem; text-decoration: none; cursor: pointer; font: inherit; font-weight: 600; }
.cover-modules { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: var(--space-4); list-style: none; margin: 0 0 var(--space-8); padding: 0; }
.cover-card { display: flex; flex-direction: column; gap: .35rem; height: 100%; padding: var(--space-5); border-radius: var(--radius-md); background: var(--color-surface);
  border: 1px solid var(--color-border-light); box-shadow: var(--shadow-sm); color: inherit; text-decoration: none;
  transition: transform var(--duration-normal) var(--ease-out), box-shadow var(--duration-normal), border-color var(--duration-fast); }
.cover-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); border-color: var(--color-accent-muted); }
.cover-card .cm-num { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--color-accent-text); font-weight: 600; }
.cover-card .cm-title { font-family: var(--font-display); font-weight: 700; font-size: var(--text-lg); line-height: 1.25; }
.cover-card .cm-sub { font-size: var(--text-sm); color: var(--color-text-secondary); }
.cover-card .cm-meta { margin-top: auto; padding-top: var(--space-2); font-size: var(--text-xs); color: var(--color-text-muted); }
.cover-hint { font-size: var(--text-sm); color: var(--color-text-secondary); max-width: 70ch; }
.cover-hint kbd { font-family: var(--font-mono); font-size: .85em; padding: .05em .4em; border: 1px solid var(--color-border); border-bottom-width: 2px; border-radius: 5px; background: var(--color-surface); }

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; scroll-snap-type: none; }
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
  .animate-in { opacity: 1; transform: none; }
}
@media print {
  .nav, .toc, .toc-backdrop, .skip-link, .cover-actions, .cover-hint { display: none !important; }
  .animate-in { opacity: 1 !important; transform: none !important; }
  .module, .cover { min-height: 0; padding-top: 1rem; }
  html { scroll-snap-type: none; }
}
"""

ASSETS = Path(__file__).resolve().parents[2] / "assets"

# ── JavaScript ───────────────────────────────────────────────────────────

INLINE_THEME_JS = ("<script>try{var t=localStorage.getItem('b2c-theme');if(t==='dark'||t==='light')"
                   "document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>")

UI_JS = (ASSETS / "book-ui.js").read_text(encoding="utf-8")

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
           "read": "read", "kicker": "Interactive course", "from": "Built from “{title}”, PDF pages {a}–{b}", "module": "module", "modules": "modules",
           "lesson": "lesson", "lessons": "lessons", "quiz": "quiz question", "quizzes": "quiz questions", "terms": "glossary terms", "term": "glossary term",
           "hint": "Tip: <kbd>↑</kbd> <kbd>↓</kbd> move between modules, <b>Contents</b> jumps to any lesson, and the moon/sun button switches the theme "
                   "(it follows your system until you choose).", "toc_nav": "Table of contents", "glossary": "Glossary"},
    "ru": {"home": "Главная", "contents": "Оглавление", "dark": "Тёмная тема", "close": "Закрыть оглавление", "skip": "К содержимому", "start": "Начать",
           "read": "прочитано", "kicker": "Интерактивный курс", "from": "Построен по книге «{title}», страницы PDF {a}–{b}", "module": "модуль", "modules": "модулей",
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
