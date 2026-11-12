"""LaTeX helpers shared by extract (draft LaTeX from PDF spans), validate and render.

Everything is deterministic and dependency-free. The LaTeX checker is a *structural* check
(braces, \\left/\\right, environments, \\frac arity, commands KaTeX does not support). It cannot
prove a formula is mathematically right or that KaTeX renders it; the course renders with
`throwOnError: false`, so an unsupported command shows as red source, not as a crash.
"""
from __future__ import annotations

import re

# ── Unicode <-> LaTeX tables ─────────────────────────────────────────────

GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ϵ": "epsilon", "ζ": "zeta",
    "η": "eta", "θ": "theta", "ϑ": "vartheta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "µ": "mu",
    "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi",
    "ϕ": "varphi", "χ": "chi", "ψ": "psi", "ω": "omega", "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta",
    "Λ": "Lambda", "Ξ": "Xi", "Π": "Pi", "Σ": "Sigma", "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
}
OPS = {
    "×": r"\times", "·": r"\cdot", "⋅": r"\cdot", "±": r"\pm", "∓": r"\mp", "≤": r"\le", "≥": r"\ge", "≈": r"\approx",
    "≠": r"\ne", "≡": r"\equiv", "∝": r"\propto", "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla", "∑": r"\sum",
    "∫": r"\int", "∮": r"\oint", "∏": r"\prod", "→": r"\to", "←": r"\leftarrow", "⇒": r"\Rightarrow", "⟨": r"\langle",
    "⟩": r"\rangle", "∈": r"\in", "′": "'", "−": "-", "–": "-", "—": "-", "°": r"^{\circ}",
    "ℏ": r"\hbar", "ℓ": r"\ell", "∼": r"\sim", "≪": r"\ll", "≫": r"\gg", "⊥": r"\perp", "∥": r"\parallel",
    "…": r"\ldots", "∀": r"\forall", "∃": r"\exists", "∅": r"\emptyset", "√": r"\sqrt",
}
SUP = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
       "⁺": "+", "⁻": "-", "ⁿ": "n"}
SUB = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
       "₊": "+", "₋": "-"}
MATH_CHARS = set(GREEK) | set(OPS) | set(SUP) | set(SUB) | set("=∑∫√±≤≥≈≠∂∇∞αβγδεθλμνπρσφψω×·⟨⟩")
# true math fonts only: CMMI/CMSY/CMEX (+bold variants), AMS symbol fonts, "...Math", Symbol. NOT CMR/CMBX/CMTI/CMSS (those are text fonts)
MATH_FONT = re.compile(r"CM(MI|SY|EX|MIB|BSY)\d|MSAM|MSBM|math|symbol|stixmath|euclid", re.I)
MONO_FONT = re.compile(r"courier|mono(?!type)|consol|menlo|typewriter|inconsolata|lucida\s?console|cmtt|lmmono|sourcecode|dejavusansmono|fira\s?code|code", re.I)

# command -> unicode, for comparing LaTeX against PDF text
CMD_TO_UNI = {f"\\{v}": k for k, v in GREEK.items() if k not in ("ϵ", "µ")}
CMD_TO_UNI.update({r"\varepsilon": "ε", r"\varphi": "φ", r"\vartheta": "θ", r"\varrho": "ρ", r"\varsigma": "σ"})
# only operators that survive text extraction reliably count as distinctive (relations like \\approx often don't)
# Text layers often turn ∑ into "X", drop ∫, or lose √/∂, so only symbols that survive extraction count as evidence.
DISTINCT_OPS = ATOM_CHARS = set("ℏ")
CMD_TO_UNI.update({v: k for k, v in OPS.items() if v.startswith("\\") and k in DISTINCT_OPS})
FUNC_NAMES = {"sin", "cos", "tan", "exp", "ln", "log", "sinh", "cosh", "tanh", "min", "max", "lim", "det", "arg"}
NORM_UNI = {"ϵ": "ε", "ϕ": "φ", "ϑ": "θ", "µ": "μ", "⋅": "·", "−": "-", "∮": "∫", "ϱ": "ρ", "ς": "σ", "∆": "Δ", "Ω": "Ω", "ħ": "ℏ"}

# ── draft LaTeX from PDF text spans (extract stage) ──────────────────────


def chars_to_tex(s: str) -> str:
    out = []
    for ch in s:
        if ch in GREEK:
            out.append("\\" + GREEK[ch] + " ")
        elif ch in OPS:
            out.append(OPS[ch] + (" " if OPS[ch].startswith("\\") else ""))
        elif ch in SUP:
            out.append("^{" + SUP[ch] + "}")
        elif ch in SUB:
            out.append("_{" + SUB[ch] + "}")
        elif ch in "{}#%&$_^~\\":
            out.append("\\" + ch if ch in "{}#%&$_" else {"^": r"\^{}", "~": r"\sim ", "\\": r"\backslash "}[ch])
        elif ch == "\u00a0" or ch in "\u2002\u2003\u2009\u202f":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _wrap_sqrt(t: str) -> str:
    """'\\sqrt (a b)' -> '\\sqrt{(a b)}' ; '\\sqrt x' -> '\\sqrt{x}'."""
    out, i = [], 0
    while True:
        j = t.find(r"\sqrt", i)
        if j < 0:
            out.append(t[i:])
            break
        out.append(t[i:j])
        k = j + 5
        while k < len(t) and t[k] == " ":
            k += 1
        if k < len(t) and t[k] == "{":
            out.append(r"\sqrt")
            i = k
            continue
        if k < len(t) and t[k] == "(":
            depth, m = 0, k
            while m < len(t):
                depth += t[m] == "("
                depth -= t[m] == ")"
                m += 1
                if depth == 0:
                    break
            out.append(r"\sqrt{" + t[k:m] + "}")
            i = m
        else:
            m = k
            while m < len(t) and (t[m].isalnum() or t[m] == "\\"):
                m += 1
            m = max(m, k + 1)
            out.append(r"\sqrt{" + t[k:m] + "}")
            i = m
    return "".join(out)


def spans_to_tex(spans: list[dict]) -> str:
    """Rebuild a LaTeX draft from one PDF line's spans using font size + baseline for sub/superscripts."""
    spans = [s for s in spans if s["text"].strip() or s["text"] == " "]
    if not spans:
        return ""
    main = max(spans, key=lambda s: (s["size"], len(s["text"].strip())))
    base_y, main_size = main["origin"][1], main["size"]
    parts: list[tuple[str, str]] = []
    for s in spans:
        lvl = "b"
        if s["size"] < 0.88 * main_size and s["text"].strip():
            dy = base_y - s["origin"][1]
            if dy > 0.22 * main_size:
                lvl = "sup"
            elif dy < -0.10 * main_size:
                lvl = "sub"
        txt = chars_to_tex(s["text"])
        if parts and parts[-1][0] == lvl:
            parts[-1] = (lvl, parts[-1][1] + txt)
        else:
            parts.append((lvl, txt))
    out = []
    for lvl, txt in parts:
        t = txt.strip() if lvl != "b" else txt
        out.append({"b": t, "sup": "^{" + t.replace(" ", "") + "}", "sub": "_{" + t.replace(" ", "") + "}"}[lvl])
    tex = "".join(out)
    tex = _wrap_sqrt(tex)
    tex = re.sub(r"\s+", " ", tex).strip()
    tex = re.sub(r"\s*([_^]\{)", r"\1", tex)
    return tex


def text_to_tex(text: str) -> str:
    """Fallback draft from plain text (OCR pages, no span geometry)."""
    return re.sub(r"\s+", " ", _wrap_sqrt(chars_to_tex(text))).strip()


# ── splitting text into text / inline-math segments ──────────────────────

_INLINE = re.compile(r"(?<!\\)\$(?!\$)(?=\S)(.+?)(?<=\S)(?<!\\)\$(?!\$)", re.S)


def split_math(text: str) -> list[tuple[str, str]]:
    """[('text','a '), ('math','x^2'), ('text',' b')]. `\\$` is a literal dollar sign."""
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        out.append(("math", m.group(1)))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return [(k, s.replace(r"\$", "$") if k == "text" else s) for k, s in out]


def unescaped_dollars(text: str) -> int:
    return len(re.findall(r"(?<!\\)\$", text))


# ── structural LaTeX check ───────────────────────────────────────────────

UNSUPPORTED = {
    r"\bm": r"\boldsymbol", r"\mathbbm": r"\mathbb", r"\label": "remove it (no equation numbering here)",
    r"\nonumber": r"\notag", r"\eqref": "write the number in words", r"\ref": "write the number in words",
    r"\cite": "cite with the page field", r"\input": "not allowed", r"\include": "not allowed", r"\def": "not allowed",
    r"\newcommand": "write the expression out", r"\renewcommand": "write the expression out",
    r"\usepackage": "not allowed", r"\SI": r"\text{value unit}", r"\si": r"\mathrm{unit}", r"\unit": r"\mathrm{unit}",
    r"\qty": r"\left(...\right)", r"\dd": r"\mathrm{d}", r"\abs": r"\left|...\right|", r"\norm": r"\left\|...\right\|",
    r"\bra": r"\langle ... |", r"\ket": r"| ... \rangle", r"\ensuremath": "remove it", r"\includegraphics": "not allowed",
    r"\url": "not allowed", r"\href": "not allowed", r"\write": "not allowed", r"\textsc": r"\text", r"\mbox": r"\text",
    r"\middle": r"\left/\right", r"\hfill": r"\quad", r"\vspace": "remove it", r"\hspace": r"\quad",
}
ENVS = {"aligned", "gathered", "cases", "matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "array", "split", "align", "align*"}
_CMD = re.compile(r"\\([A-Za-z]+\*?|.)")
MAX_INLINE, MAX_BLOCK = 160, 600


def check_latex(src: str, display: bool = True) -> list[str]:
    errs: list[str] = []
    s = src.strip()
    if not s:
        return ["empty formula"]
    if len(s) > (MAX_BLOCK if display else MAX_INLINE):
        errs.append(f"formula is {len(s)} chars (max {MAX_BLOCK if display else MAX_INLINE}); split it or describe it in words")
    if re.search(r"[\x00-\x09\x0b-\x1f]", src.strip(" ")) or ("\n" in s and not display):
        errs.append("control character in the formula: a single backslash in the JSON file turned \\t/\\f/\\b/\\r/\\n into "
                    "a tab/form-feed/etc. (e.g. \\theta, \\frac, \\beta, \\rho, \\nu, \\times); double every backslash")
    if "$" in re.sub(r"\\\$", "", s):
        errs.append("unescaped $ inside a formula")
    if "%" in re.sub(r"\\%", "", s):
        errs.append("unescaped % starts a LaTeX comment; write \\%")
    if "\n" in s and display and not re.search(r"\\begin\{", s):
        errs.append("newline inside a formula; use aligned/cases or \\\\ explicitly")
    # braces
    depth = 0
    for i, ch in enumerate(re.sub(r"\\[{}]", "", s)):
        depth += ch == "{"
        depth -= ch == "}"
        if depth < 0:
            errs.append("closing } without opening {")
            break
    if depth > 0:
        errs.append(f"{depth} unclosed {{")
    # \left / \right
    nl, nr = len(re.findall(r"\\left\b", s)), len(re.findall(r"\\right\b", s))
    if nl != nr:
        errs.append(f"\\left count ({nl}) != \\right count ({nr})")
    # environments
    stack = []
    for m in re.finditer(r"\\(begin|end)\{([^}]*)\}", s):
        kind, name = m.groups()
        if name not in ENVS:
            errs.append(f"environment {{{name}}} is not supported (use one of {sorted(ENVS)})")
        if kind == "begin":
            stack.append(name)
        elif not stack or stack.pop() != name:
            errs.append(f"\\end{{{name}}} does not match a \\begin")
    if stack:
        errs.append(f"\\begin{{{stack[-1]}}} is never closed")
    # unsupported commands
    seen = set()
    for m in _CMD.finditer(s):
        c = "\\" + m.group(1)
        if c in UNSUPPORTED and c not in seen:
            seen.add(c)
            errs.append(f"{c} is not supported by KaTeX: {UNSUPPORTED[c]}")
    # \frac & friends need two arguments
    for m in re.finditer(r"\\(?:d|t)?frac\b|\\binom\b", s):
        if _count_args(s, m.end(), 2) < 2:
            errs.append(f"{m.group(0)} needs two arguments")
    for m in re.finditer(r"\\(?:sqrt)\b(?!\[)", s):
        if _count_args(s, m.end(), 1) < 1:
            errs.append("\\sqrt needs an argument")
    if re.search(r"[_^]\s*(?:$|[}\s&])", s) or re.search(r"[_^]\s*[_^]", s):
        errs.append("dangling _ or ^ (missing sub/superscript, or double ^^ / __)")
    return errs


def _count_args(s: str, pos: int, want: int) -> int:
    n, i = 0, pos
    while n < want:
        while i < len(s) and s[i] == " ":
            i += 1
        if i >= len(s):
            break
        if s[i] == "{":
            depth, j = 0, i
            while j < len(s):
                if s[j] == "{" and (j == 0 or s[j - 1] != "\\"):
                    depth += 1
                elif s[j] == "}" and (j == 0 or s[j - 1] != "\\"):
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth != 0:
                break
            i = j + 1
        elif s[i] == "\\":
            m = _CMD.match(s, i)
            i = m.end() if m else i + 1
        elif s[i] in "}&":
            break
        else:
            i += 1
        n += 1
    return n


# ── atoms: loose grounding of a formula against page text ────────────────

_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")


def latex_atoms(tex: str) -> set[str]:
    """Distinctive symbols in a LaTeX formula: greek letters, operators, function names, numbers >= 2 digits."""
    atoms: set[str] = set()
    for m in _CMD.finditer(tex):
        c = "\\" + m.group(1)
        if c in CMD_TO_UNI:
            atoms.add(NORM_UNI.get(CMD_TO_UNI[c], CMD_TO_UNI[c]))
        elif m.group(1) in FUNC_NAMES:
            atoms.add(m.group(1))
    for ch in tex:
        if ch in GREEK or ch in ATOM_CHARS:
            atoms.add(NORM_UNI.get(ch, ch))
    atoms |= {n for n in _NUM.findall(tex) if len(n) >= 2 or "." in n}
    return atoms


def fix_glyphs(text: str) -> str:
    """Unify glyph variants the PDF text layer produces: ∆ (increment) -> Δ, ħ / ¯h / h + combining macron -> ℏ, ohm -> Ω."""
    text = re.sub(r"(?:¯|\u02c9|\u0304)\s?h|h\u0304|ħ", "ℏ", text)
    return text.replace("\u2206", "Δ").replace("\u2126", "Ω")


def text_atoms(text: str) -> set[str]:
    text = fix_glyphs(text)
    atoms: set[str] = set()
    for ch in text:
        if ch in GREEK or ch in ATOM_CHARS:
            atoms.add(NORM_UNI.get(ch, ch))
    atoms |= {w for w in re.findall(r"[a-z]{2,}", text.lower()) if w in FUNC_NAMES}
    atoms |= {n for n in _NUM.findall(text) if len(n) >= 2 or "." in n}
    # extractors sometimes spell out the command names of a symbol font
    for name, uni in ((v, k) for k, v in GREEK.items()):
        if re.search(rf"(?<![a-z]){name}(?![a-z])", text):
            atoms.add(NORM_UNI.get(uni, uni))
    return atoms


def grounding(tex: str, page_text: str) -> tuple[float | None, set[str]]:
    """(share of the formula's distinctive atoms found on the cited page, missing atoms); None if no atoms."""
    a = latex_atoms(tex)
    if not a:
        return None, set()
    have = text_atoms(page_text)
    miss = a - have
    return (len(a) - len(miss)) / len(a), miss
