"""Diagrams drawn for the course from a small JSON spec (deterministic SVG, no dependencies, no LLM-written SVG).

Two kinds:
  flow  nodes + edges -> boxes and arrows; layered auto-layout; loops (back edges) are drawn as return arcs.
        Use for algorithms, pipelines, cause->effect chains ("assign charge -> solve field -> push particles -> repeat").
  plot  one or more y = f(x) curves (+ optional points) with axes, ticks, legend; linear or log scales.
        Expressions use x, pi, e and sin cos tan exp log sqrt abs sinh cosh tanh with + - * / ** only (checked by a whitelist).
Colours come from CSS classes so the SVG follows the course theme. These are *illustrations made for the course*, labelled as such
by the renderer; they are not the book's figures (those are `figure` blocks).
"""
from __future__ import annotations

import ast
import html
import math
import textwrap

FUNCS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp, "log": math.log, "sqrt": math.sqrt,
         "abs": abs, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh}
CONSTS = {"pi": math.pi, "e": math.e}
MAX_EXPR, MAX_NODES_AST = 120, 45


# ── validation ───────────────────────────────────────────────────────────

def _check_expr(expr: str) -> str | None:
    if not isinstance(expr, str) or not expr.strip():
        return "empty expression"
    if len(expr) > MAX_EXPR:
        return f"expression longer than {MAX_EXPR} chars"
    if "^" in expr:
        return f"{expr!r}: write powers with ** (x**2), not ^"
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        return f"syntax error in {expr!r}: {e.msg} (use ** for powers, no ^)"
    n = 0
    for node in ast.walk(tree):
        n += 1
        if isinstance(node, (ast.Expression, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)):
            continue
        if isinstance(node, ast.BinOp) or isinstance(node, ast.UnaryOp):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            continue
        if isinstance(node, ast.Name) and (node.id == "x" or node.id in CONSTS or node.id in FUNCS):
            continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and not node.keywords:
            continue
        return f"{type(node).__name__} is not allowed in {expr!r}; allowed: x, pi, e, {', '.join(sorted(FUNCS))}, + - * / **"
    if n > MAX_NODES_AST:
        return "expression too complex"
    return None


class _Floats(ast.NodeTransformer):
    """int literals -> float, so `9**9**9` overflows quickly instead of building a huge integer."""

    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(float(node.value)), node) if isinstance(node.value, int) else node


def _compile(expr: str):
    tree = ast.fix_missing_locations(_Floats().visit(ast.parse(expr.strip(), mode="eval")))
    code = compile(tree, "<expr>", "eval")
    env = {"__builtins__": {}, **FUNCS, **CONSTS}

    def f(x: float) -> float | None:
        try:
            v = eval(code, env, {"x": x})  # noqa: S307 - whitelisted AST, no builtins
            return float(v) if math.isfinite(v) and abs(v) < 1e12 else None
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            return None

    return f


def check_diagram(d: dict) -> list[str]:
    errs: list[str] = []
    kind = d.get("kind")
    for k in ("title", "caption"):
        if "$" in str(d.get(k, "")):
            errs.append(f"{k}: diagrams take plain text, no $math$ (use Unicode symbols such as λ, φ, ²)")
    if kind == "flow":
        nodes, edges = d.get("nodes", []), d.get("edges", [])
        if not 2 <= len(nodes) <= 10:
            errs.append(f"flow needs 2-10 nodes, has {len(nodes)}")
        ids = [n.get("id") for n in nodes]
        if len(set(ids)) != len(ids) or any(not i for i in ids):
            errs.append("node ids must be unique and non-empty")
        for n in nodes:
            lab = str(n.get("label", ""))
            if not lab.strip() or len(lab) > 44:
                errs.append(f"node {n.get('id')!r}: label must be 1-44 chars")
            if "$" in lab:
                errs.append(f"node {n.get('id')!r}: no $math$ in labels")
        if not edges:
            errs.append("flow needs at least one edge")
        for e in edges:
            if e.get("from") not in ids or e.get("to") not in ids:
                errs.append(f"edge {e.get('from')!r}->{e.get('to')!r} references an unknown node id")
            if e.get("from") == e.get("to"):
                errs.append("self-loops are not supported; draw the repeat as an edge back to an earlier node")
            if len(str(e.get("label", ""))) > 24:
                errs.append("edge labels are at most 24 chars")
        if d.get("direction", "LR") not in ("LR", "TB"):
            errs.append("direction must be LR or TB")
    elif kind == "plot":
        series = d.get("series", [])
        if not 1 <= len(series) <= 4:
            errs.append("plot needs 1-4 series")
        x = d.get("x", {})
        if not all(isinstance(x.get(k), (int, float)) for k in ("min", "max")) or x.get("min", 0) >= x.get("max", 0):
            errs.append("x needs numeric min < max")
        else:
            for ax in ("x", "y"):
                a = d.get(ax, {})
                if a.get("scale", "linear") not in ("linear", "log"):
                    errs.append(f"{ax}.scale must be linear or log")
                if a.get("scale") == "log" and isinstance(a.get("min"), (int, float)) and a["min"] <= 0:
                    errs.append(f"{ax} log scale needs min > 0")
                if "$" in str(a.get("label", "")):
                    errs.append(f"{ax}.label: plain text only")
            for s in series:
                msg = _check_expr(s.get("expr"))
                if msg:
                    errs.append(f"series {s.get('label')!r}: {msg}")
                    continue
                f = _compile(s["expr"])
                lo, hi = x["min"], x["max"]
                ok = sum(1 for i in range(40) if f(lo + (hi - lo) * i / 39) is not None)
                if ok < 20:
                    errs.append(f"series {s.get('label')!r}: {s['expr']!r} is undefined or too large on most of [{lo}, {hi}]")
                if not str(s.get("label", "")).strip():
                    errs.append("every series needs a label")
        for p in d.get("points", []):
            if not all(isinstance(p.get(k), (int, float)) for k in ("x", "y")):
                errs.append("points need numeric x and y")
                break
    else:
        errs.append("diagram.kind must be 'flow' or 'plot'")
    return errs


# ── SVG helpers ──────────────────────────────────────────────────────────

def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _wrap(label: str, width: int = 18) -> list[str]:
    return textwrap.wrap(label, width=width, break_long_words=True)[:3] or [label]


MARKER = ('<defs><marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
          '<path d="M0,0 L10,5 L0,10 z" class="dg-arrow"/></marker></defs>')


# ── flow ─────────────────────────────────────────────────────────────────

def _layers(nodes: list[str], edges: list[tuple[str, str]]):
    """Longest-path layering after removing back edges found by DFS. Returns (layer_of, back_edges)."""
    adj = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)
    state: dict[str, int] = {}
    back: set[tuple[str, str]] = set()

    def dfs(u: str) -> None:
        state[u] = 1
        for v in adj[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                dfs(v)
        state[u] = 2

    indeg = {n: 0 for n in nodes}
    for a, b in edges:
        indeg[b] += 1
    for n in [n for n in nodes if indeg[n] == 0] + nodes:
        if n not in state:
            dfs(n)
    layer = {n: 0 for n in nodes}
    for _ in range(len(nodes)):
        for a, b in edges:
            if (a, b) not in back and layer[b] < layer[a] + 1:
                layer[b] = layer[a] + 1
    return layer, back


def render_flow(d: dict, uid: str) -> str:
    nodes = d["nodes"]
    ids = [n["id"] for n in nodes]
    label = {n["id"]: n["label"] for n in nodes}
    edges = [(e["from"], e["to"]) for e in d["edges"]]
    elabel = {(e["from"], e["to"]): e.get("label", "") for e in d["edges"]}
    layer, back = _layers(ids, edges)
    lines = {i: _wrap(label[i]) for i in ids}
    bw = max(max(len(x) for x in ls) for ls in lines.values()) * 7.4 + 28
    bh = 22 + 16 * max(len(ls) for ls in lines.values())
    gapx, gapy = 56, 30
    horiz = d.get("direction", "LR") == "LR"
    cols: dict[int, list[str]] = {}
    for i in ids:
        cols.setdefault(layer[i], []).append(i)
    nl, widest = len(cols), max(len(v) for v in cols.values())
    pos: dict[str, tuple[float, float]] = {}
    pad = 26
    for L, members in cols.items():
        for k, i in enumerate(members):
            off = (widest - len(members)) / 2
            if horiz:
                pos[i] = (pad + L * (bw + gapx), pad + (k + off) * (bh + gapy))
            else:
                pos[i] = (pad + (k + off) * (bw + gapx), pad + L * (bh + gapy + 14))
    W = (nl * bw + (nl - 1) * gapx if horiz else widest * bw + (widest - 1) * gapx) + 2 * pad
    H = (widest * bh + (widest - 1) * gapy if horiz else nl * bh + (nl - 1) * (gapy + 14)) + 2 * pad
    ret = 38 if back else 0
    H += ret if horiz else 0
    W += ret if not horiz else 0
    mid = f"mk-{uid}"
    out = [f'<svg class="dg dg-flow" viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="{_e(d.get("title", "diagram"))}" '
           f'style="max-width:{W:.0f}px">', MARKER.format(id=mid)]

    def anchor(i: str, toward: tuple[float, float]) -> tuple[float, float]:
        x, y = pos[i]
        cx, cy = x + bw / 2, y + bh / 2
        tx, ty = toward
        if horiz:
            return (x + bw, cy) if tx > cx else (x, cy) if tx < cx else ((cx, y + bh) if ty > cy else (cx, y))
        return (cx, y + bh) if ty > cy else (cx, y) if ty < cy else ((x + bw, cy) if tx > cx else (x, cy))

    for a, b in edges:
        ax, ay = pos[a]
        bx, by = pos[b]
        ca, cb = (ax + bw / 2, ay + bh / 2), (bx + bw / 2, by + bh / 2)
        if (a, b) in back:
            if horiz:
                y2 = max(ay, by) + bh + ret * 0.8
                p0, p1 = (ca[0], ay + bh), (cb[0], by + bh)
                path = f"M{p0[0]:.1f},{p0[1]:.1f} C{p0[0]:.1f},{y2:.1f} {p1[0]:.1f},{y2:.1f} {p1[0]:.1f},{p1[1] + 2:.1f}"
                lx, ly = (p0[0] + p1[0]) / 2, y2 - 4
            else:
                x2 = max(ax, bx) + bw + ret * 0.8
                p0, p1 = (ax + bw, ca[1]), (bx + bw, cb[1])
                path = f"M{p0[0]:.1f},{p0[1]:.1f} C{x2:.1f},{p0[1]:.1f} {x2:.1f},{p1[1]:.1f} {p1[0] + 2:.1f},{p1[1]:.1f}"
                lx, ly = x2 + 4, (p0[1] + p1[1]) / 2
            out.append(f'<path d="{path}" class="dg-edge dg-back" marker-end="url(#{mid})"/>')
        else:
            p0, p1 = anchor(a, cb), anchor(b, ca)
            out.append(f'<line x1="{p0[0]:.1f}" y1="{p0[1]:.1f}" x2="{p1[0]:.1f}" y2="{p1[1]:.1f}" class="dg-edge" marker-end="url(#{mid})"/>')
            lx, ly = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - 6
        if elabel[(a, b)]:
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="dg-elabel" text-anchor="middle">{_e(elabel[(a, b)])}</text>')
    for i in ids:
        x, y = pos[i]
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="10" class="dg-node dg-n{layer[i] % 5}"/>')
        n = len(lines[i])
        for k, ln in enumerate(lines[i]):
            ty = y + bh / 2 + (k - (n - 1) / 2) * 16 + 5
            out.append(f'<text x="{x + bw / 2:.1f}" y="{ty:.1f}" class="dg-label" text-anchor="middle">{_e(ln)}</text>')
    out.append("</svg>")
    return "".join(out)


# ── plot ─────────────────────────────────────────────────────────────────

def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    span = hi - lo
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9 * span:
        out.append(round(t, 12))
        t += step
    return out


def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 1e4 or abs(v) < 1e-3:
        return f"{v:.0e}".replace("e+0", "e").replace("e-0", "e-").replace("e+", "e")
    return f"{v:.4g}"


def render_plot(d: dict, uid: str) -> str:
    W, H, ml, mr, mt, mb = 640, 360, 62, 20, 18, 58
    xa, ya = d["x"], d.get("y", {})
    xlog, ylog = xa.get("scale") == "log", ya.get("scale") == "log"
    N = 240
    curves = []
    for s in d["series"]:
        f = _compile(s["expr"])
        pts = []
        for i in range(N):
            x = (xa["min"] * (xa["max"] / xa["min"]) ** (i / (N - 1))) if xlog else xa["min"] + (xa["max"] - xa["min"]) * i / (N - 1)
            y = f(x)
            pts.append((x, y if y is not None and (not ylog or y > 0) else None))
        curves.append((s["label"], pts))
    ys = sorted(y for _, pts in curves for _, y in pts if y is not None)
    ys += [p["y"] for p in d.get("points", [])]
    ys.sort()
    if "min" in ya and "max" in ya:
        y0, y1 = ya["min"], ya["max"]
    elif ys:
        lo_i, hi_i = int(0.02 * (len(ys) - 1)), int(0.98 * (len(ys) - 1))
        y0, y1 = ys[lo_i], ys[hi_i]
        if ylog:
            y0, y1 = 10 ** math.floor(math.log10(max(y0, 1e-300))), 10 ** math.ceil(math.log10(max(y1, 1e-300)))
        else:
            pad = (y1 - y0) * 0.06 or 1
            y0, y1 = (0 if y0 >= 0 and y0 < 0.3 * y1 else y0 - pad), y1 + pad
    else:
        y0, y1 = 0, 1
    if y1 <= y0:
        y1 = y0 + 1

    def sx(x): return ml + ((math.log(x / xa["min"]) / math.log(xa["max"] / xa["min"])) if xlog else (x - xa["min"]) / (xa["max"] - xa["min"])) * (W - ml - mr)
    def sy(y): return H - mb - ((math.log(y / y0) / math.log(y1 / y0)) if ylog else (y - y0) / (y1 - y0)) * (H - mt - mb)

    def ticks(lo, hi, log):
        if log:
            e0, e1 = math.ceil(math.log10(lo) - 1e-9), math.floor(math.log10(hi) + 1e-9)
            return [10.0 ** k for k in range(e0, e1 + 1)] or [lo, hi]
        return _nice_ticks(lo, hi)

    out = [f'<svg class="dg dg-plot" viewBox="0 0 {W} {H}" role="img" aria-label="{_e(d.get("title", "plot"))}">']
    for t in ticks(xa["min"], xa["max"], xlog):
        x = sx(t)
        out.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{H - mb}" class="dg-grid"/>'
                   f'<text x="{x:.1f}" y="{H - mb + 16}" class="dg-tick" text-anchor="middle">{_fmt(t)}</text>')
    for t in ticks(y0, y1, ylog):
        if y0 - 1e-12 <= t <= y1 + 1e-12:
            y = sy(t)
            out.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W - mr}" y2="{y:.1f}" class="dg-grid"/>'
                       f'<text x="{ml - 8}" y="{y + 4:.1f}" class="dg-tick" text-anchor="end">{_fmt(t)}</text>')
    out.append(f'<rect x="{ml}" y="{mt}" width="{W - ml - mr}" height="{H - mt - mb}" class="dg-frame"/>')
    out.append(f'<clipPath id="cp-{uid}"><rect x="{ml}" y="{mt}" width="{W - ml - mr}" height="{H - mt - mb}"/></clipPath>')
    for k, (lab, pts) in enumerate(curves):
        seg, paths = [], []
        for x, y in pts:
            if y is None:
                if len(seg) > 1:
                    paths.append(seg)
                seg = []
            else:
                seg.append((sx(x), max(min(sy(y), H * 3), -H * 2)))
        if len(seg) > 1:
            paths.append(seg)
        for sg in paths:
            dd = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in sg)
            out.append(f'<path d="{dd}" class="dg-line dg-s{k}" clip-path="url(#cp-{uid})"/>')
    for p in d.get("points", []):
        if (not xlog or p["x"] > 0) and (not ylog or p["y"] > 0):
            out.append(f'<circle cx="{sx(p["x"]):.1f}" cy="{sy(p["y"]):.1f}" r="3.6" class="dg-pt" clip-path="url(#cp-{uid})"/>')
    out.append(f'<text x="{(ml + W - mr) / 2:.0f}" y="{H - 10}" class="dg-axis" text-anchor="middle">{_e(xa.get("label", ""))}</text>')
    out.append(f'<text transform="translate(16,{(mt + H - mb) / 2:.0f}) rotate(-90)" class="dg-axis" text-anchor="middle">{_e(ya.get("label", ""))}</text>')
    lx = ml + 12
    for k, (lab, _) in enumerate(curves):
        ly = mt + 16 + k * 18
        out.append(f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 22}" y2="{ly - 4}" class="dg-line dg-s{k}"/>'
                   f'<text x="{lx + 28}" y="{ly}" class="dg-legend">{_e(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def render_svg(d: dict, uid: str) -> str:
    return render_flow(d, uid) if d["kind"] == "flow" else render_plot(d, uid)


CSS = """/* diagrams (book-to-course) */
.diagram, .book-figure { margin: 2rem 0; padding: 1rem 1.25rem 1.1rem; background: var(--color-surface); border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm); }
.diagram svg { width: 100%; height: auto; display: block; margin: 0 auto; }
.diagram figcaption, .book-figure figcaption { margin-top: .7rem; font-size: .92rem; color: var(--color-text-secondary); }
.diagram .fig-title { font-family: var(--font-display); font-weight: 600; margin: 0 0 .5rem; }
.fig-tag { display: inline-block; margin-right: .5em; padding: 0 .55em; font-size: .72em; line-height: 1.8; border-radius: 999px;
  background: var(--color-accent-light); color: var(--color-accent-text); font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.book-figure img { display: block; max-width: 100%; height: auto; margin: 0 auto; border-radius: 6px; background: #fff; }
.dg text { font-family: var(--font-body); }
.dg-node { fill: var(--color-bg); stroke: var(--color-accent); stroke-width: 2; }
.dg-n1 { stroke: var(--color-actor-1, var(--color-accent)); } .dg-n2 { stroke: var(--color-actor-2, var(--color-accent)); }
.dg-n3 { stroke: var(--color-actor-3, var(--color-accent)); } .dg-n4 { stroke: var(--color-actor-4, var(--color-accent)); }
.dg-label { font-size: 14px; fill: var(--color-text); } .dg-elabel { font-size: 12px; fill: var(--color-text-secondary); }
.dg-edge { stroke: var(--color-text-secondary); stroke-width: 2; fill: none; } .dg-back { stroke-dasharray: 6 4; stroke: var(--color-accent); }
.dg-arrow { fill: var(--color-text-secondary); }
.dg-grid { stroke: var(--color-border); stroke-width: 1; } .dg-frame { fill: none; stroke: var(--color-text-secondary); stroke-width: 1.2; }
.dg-tick { font-size: 11px; fill: var(--color-text-secondary); } .dg-axis { font-size: 13px; fill: var(--color-text); }
.dg-legend { font-size: 13px; fill: var(--color-text); }
.dg-line { fill: none; stroke-width: 2.6; stroke-linejoin: round; stroke-linecap: round; }
.dg-s0 { stroke: var(--color-actor-1); }
.dg-s1 { stroke: var(--color-actor-2); stroke-dasharray: 9 6; }
.dg-s2 { stroke: var(--color-actor-3); stroke-dasharray: 2 6; }
.dg-s3 { stroke: var(--color-actor-5); stroke-dasharray: 12 5 2 5; }
.dg-pt { fill: var(--color-text); stroke: var(--color-bg); stroke-width: 1.5; }
"""
