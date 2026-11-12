#!/usr/bin/env python3
"""Find safely deletable disk space on macOS, Linux and Windows (stdlib only, Python 3.9+).

`scan` is read-only and prints a ranked table. `clean safe|rebuild|<path part>` deletes only items from the last scan,
never ones marked `review`, and only with --yes (otherwise a dry run).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOME = Path(os.environ.get("DC_HOME") or Path.home())
STATE = HOME / ".cache" / "disk-cleanup" / "last.json"

# safe = regenerates by itself; rebuild = costs a re-download/rebuild; review = may hold your data, never auto-deleted
KNOWN: list[tuple[str, str, str]] = [
    (".Trash", "safe", "Trash"),
    ("Library/Caches/uv", "rebuild", "uv downloads"),
    ("Library/Caches/ms-playwright", "rebuild", "Playwright browsers"),
    ("Library/Caches/deno", "rebuild", "Deno downloads"),
    ("Library/Caches/go-build", "rebuild", "Go build cache (slower next build)"),
    ("Library/Caches/*", "safe", "app cache"),
    ("Library/Logs", "safe", "logs"),
    ("Library/Developer/Xcode/DerivedData", "safe", "Xcode build output"),
    ("Library/Developer/CoreSimulator/Caches", "safe", "simulator cache"),
    ("Library/Developer/Xcode/iOS DeviceSupport", "rebuild", "re-created when a device is plugged in"),
    ("Library/Developer/CoreSimulator/Devices", "review", "simulator data; try `xcrun simctl delete unavailable`"),
    ("Library/Developer/Xcode/Archives", "review", "app archives"),
    ("Library/Application Support/MobileSync/Backup", "review", "iPhone backups"),
    ("Library/Containers/com.docker.docker", "review", "Docker; use `docker system prune`"),
    # Linux (XDG / Flatpak)
    (".local/share/Trash", "safe", "Trash"),
    (".var/app/*/cache", "safe", "Flatpak app cache"),
    (".local/share/Steam", "review", "Steam games"),
    (".local/share/containers", "review", "Podman images; use `podman system prune`"),
    # Windows
    ("AppData/Local/Temp", "safe", "temp files"),
    ("AppData/Local/CrashDumps", "safe", "crash dumps"),
    ("AppData/Local/Microsoft/Windows/INetCache", "safe", "browser cache"),
    ("AppData/Local/npm-cache", "safe", "npm cache"),
    ("AppData/Local/pip/Cache", "rebuild", "pip cache"),
    ("AppData/Local/go-build", "rebuild", "Go build cache (slower next build)"),
    ("AppData/Local/Docker", "review", "Docker; use `docker system prune`"),
    # cross-platform dev tools
    (".npm/_cacache", "safe", "npm cache"),
    (".cache/*", "rebuild", "pip/uv/huggingface/... cache"),
    ("go/pkg/mod/cache", "rebuild", "Go module cache"),
    (".cargo/registry", "rebuild", "Cargo downloads"),
    (".gradle/caches", "rebuild", "Gradle cache"),
    (".m2/repository", "rebuild", "Maven cache"),
    (".ivy2/cache", "rebuild", "Ivy/sbt cache"),
    (".terraform.d/plugin-cache", "rebuild", "Terraform providers"),
    (".nuget/packages", "rebuild", "NuGet packages"),
    ("Library/Application Support/*", "review", "app data"),
    ("Library/Group Containers/*", "review", "app data"),
    ("Library/Android", "review", "Android SDK/AVDs"),
    ("Downloads/*", "review", "Downloads"),
    (".colima", "review", "Colima Docker VM disk; `docker system prune -a` then `colima delete`"),
    (".rustup/toolchains/*", "review", "Rust toolchain; `rustup toolchain list`"),
]
# Project dirs found by walking ~: name -> (how to rebuild, manifests of which one must sit beside it).
# Without a manifest the dir cannot be rebuilt, so it is labelled `review`.
PY = ("pyproject.toml", "requirements.txt", "uv.lock", "setup.py")
PROJECT: dict[str, tuple[str, tuple[str, ...]]] = {
    "node_modules": ("npm/pnpm install", ("package.json",)),
    ".venv": ("uv sync / pip install", PY),
    "venv": ("pip install", PY),
    ".terraform": ("terraform init", ("main.tf", "versions.tf")),
    ".next": ("next build", ("package.json",)),
    "target": ("cargo/mvn/sbt build", ("Cargo.toml", "pom.xml", "build.sbt")),
}
MAX_DEPTH = 8
# OS app-data roots: covered by KNOWN globs, too big and private to walk for projects
SKIP_WALK = ("Library", "AppData", "go/pkg")


GROUPS = [
    ("safe", "SAFE TO DELETE", "apps recreate these by themselves"),
    ("rebuild", "DELETE, BUT COSTS A RE-DOWNLOAD/REBUILD", "nothing is lost, the next use is slower"),
    ("review", "YOUR DECISION", "may hold your data; the tool will never delete these"),
]


def du_kb(p: Path) -> int:
    if shutil.which("du"):  # fast path on macOS/Linux
        r = subprocess.run(["du", "-sk", str(p)], capture_output=True, text=True, check=False)
        return int(r.stdout.split()[0]) if r.stdout else 0
    total = 0  # Windows: no du, sum file sizes
    for dp, _, fns in os.walk(p) if p.is_dir() else [(str(p.parent), [], [p.name])]:
        for f in fns:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total // 1024


def sizes(paths: list[Path]) -> list[int]:
    with ThreadPoolExecutor(8) as ex:
        return list(ex.map(du_kb, paths))


def human(kb: int) -> str:
    n = float(kb)
    for u in ("K", "M", "G", "T"):
        if n < 1024 or u == "T":
            return f"{n:.1f}{u}" if u != "K" else f"{int(n)}K"
        n /= 1024
    return ""


def walk(big_kb: int) -> list[tuple[Path, str, str, str]]:
    """Return (path, kind, safety, note) for project dirs and big files under ~ (skips SKIP_WALK and hidden dirs)."""
    out: list[tuple[Path, str, str, str]] = []
    skip = {HOME / s for s in SKIP_WALK}
    for dp, dns, fns in os.walk(HOME):
        d = Path(dp)
        keep = []
        for n in dns:
            p = d / n
            if p.is_symlink():
                continue
            if n in PROJECT:
                note, manifests = PROJECT[n]
                ok = any((d / m).exists() for m in manifests)
                out.append((p, "found", "rebuild" if ok else "review", note if ok else f"no {manifests[0]} etc. to rebuild from"))
            elif not n.startswith(".") and p not in skip:
                keep.append(n)
        dns[:] = keep if len(d.parts) - len(HOME.parts) < MAX_DEPTH else []
        for f in fns:
            try:
                st = (d / f).lstat()
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_size // 1024 >= big_kb:
                out.append((d / f, "file", "review", "big file"))
    return out


def scan(min_mb: float, big_mb: float, top: int, overview: bool) -> None:
    cand: list[tuple[Path, str, str, str]] = []
    for pat, safety, note in KNOWN:
        cand += [(p, "known", safety, note) for p in HOME.glob(pat)]
    cand += walk(int(big_mb * 1024))
    seen: set[Path] = set()
    cand = [c for c in cand if not (c[0] in seen or seen.add(c[0]))]
    kbs = sizes([c[0] for c in cand])
    rows = sorted(((kb, *c) for kb, c in zip(kbs, cand) if kb >= min_mb * 1024), key=lambda r: -r[0])
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps([
            {"id": i, "path": str(p), "kb": kb, "kind": kind, "safety": s, "note": note}
            for i, (kb, p, kind, s, note) in enumerate(rows, 1)
        ])
    )
    du = shutil.disk_usage(HOME)
    print(f"Disk: {human(du.free // 1024)} free of {human(du.total // 1024)}")
    for safety, title, blurb in GROUPS:
        grp = [r for r in rows if r[3] == safety]
        print(f"\n== {title}: {human(sum(r[0] for r in grp))} in {len(grp)} items - {blurb}")
        for kb, p, _, _, note in grp[:top]:
            print(f"{human(kb):>8}  {str(p).replace(str(HOME), '~')}  # {note}")
        if len(grp) > top:
            print(f"{'':>8}  ... {len(grp) - top} more (raise --top)")
    print("\nDelete: disk_cleanup.py clean safe rebuild --yes   (or names like 'Caches/uv'; omit --yes for a dry run)")
    if overview:
        for label, base in (("~", HOME), *((f"~/{s}", HOME / s) for s in ("Library", "AppData", ".local/share"))):
            kids = [k for k in base.iterdir() if not k.is_symlink()] if base.exists() else []
            top8 = sorted(zip(sizes(kids), kids), key=lambda t: -t[0])[:8]
            print(f"\nlargest in {label}:")
            for kb, k in top8:
                print(f"{human(kb):>8}  {k.name}")


def clean(selectors: list[str], yes: bool) -> int:
    items = json.loads(STATE.read_text()) if STATE.exists() else []
    rc = 0
    free0 = shutil.disk_usage(HOME).free
    picked: dict[str, dict[str, object]] = {}
    for sel in selectors:
        frag = sel.replace("\\", "/")  # match 'Caches/uv' on Windows paths too
        hits = [
            i
            for i in items
            if i["safety"] == sel or (sel not in ("safe", "rebuild", "review") and frag in Path(i["path"]).as_posix())
        ]
        if not hits:
            print(f"{sel}: nothing in the last scan matches (run scan first)", file=sys.stderr)
            rc = 1
        for it in hits:
            if it["safety"] == "review":
                print(f"{it['path']} is 'review' - delete it yourself", file=sys.stderr)
                rc = 1
            else:
                picked[it["path"]] = it
    for it in picked.values():
        p = Path(it["path"])
        if HOME not in p.parents or not p.exists() or p.is_symlink():
            print(f"refusing {p}", file=sys.stderr)
            rc = 1
            continue
        print(f"{'delete' if yes else 'dry run'}: {p} ({human(it['kb'])})")
        if not yes:
            continue
        # known caches: empty the directory but keep it; found project dirs: remove whole
        for t in [p] if it["kind"] == "found" else list(p.iterdir()):
            try:
                shutil.rmtree(t) if t.is_dir() and not t.is_symlink() else t.unlink()
            except OSError as e:
                print(f"  skipped {t}: {e.strerror}", file=sys.stderr)
    if yes:
        print(f"disk free changed by {human((shutil.disk_usage(HOME).free - free0) // 1024)}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--min-mb", type=float, default=100)
    s.add_argument("--big-mb", type=float, default=500)
    s.add_argument("--top", type=int, default=15, help="rows per group")
    s.add_argument("--overview", action="store_true", help="also list biggest dirs in ~ (slow, minutes)")
    c = sub.add_parser("clean")
    c.add_argument("selectors", nargs="+", help="safe | rebuild | part of a path, e.g. Caches/uv")
    c.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "scan":
        scan(a.min_mb, a.big_mb, a.top, a.overview)
        return 0
    return clean(a.selectors, a.yes)


if __name__ == "__main__":
    sys.exit(main())
