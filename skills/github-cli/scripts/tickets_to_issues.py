#!/usr/bin/env python3
"""Push ticket files to GitHub Issues of the repo in the current directory (`gh` must be logged in).

A ticket file is `NN-slug.md` (or `EPIC/NN-slug.md`, folder `Epic_10_Web_app`) that starts with `# NN: Title` and
may contain a line `**Status:** done`. Issue title: `[10/07] Title` (`[07]` without an epic folder); body: the file;
label: the epic folder name; the issue is closed when the Status is `done`. Safe to rerun: an issue whose title exists
is left alone, or with --update its body is rewritten when it differs from the file.

  python3 tickets_to_issues.py DIR            # dry run: print what would be created or rewritten
  python3 tickets_to_issues.py DIR --create   # create the missing issues
  python3 tickets_to_issues.py DIR --update   # also rewrite issues whose body differs from the file
"""

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def rel(path: Path) -> Path:
    """Relative to the repo (the current directory) when the file lies inside it."""
    return path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path


def read(path: Path) -> tuple[str, str, str | None, bool]:
    """(title, body, label, done) of one ticket file."""
    text = path.read_text()
    head = re.match(r"# (\d+): (.*)", text)
    epic = re.match(r"Epic_(\d+)_(.*)", path.parent.name)
    num = f"{int(epic[1])}/{head[1]}" if epic else head[1]
    label = f"Epic {epic[1]}: {epic[2].replace('_', ' ')}"[:50] if epic else None
    status = re.search(r"^\*\*Status:\*\* (\w+)", text, re.M)
    body = text.split("\n", 1)[1].lstrip() + f"\n\n---\nTicket file: `{rel(path)}`\n"
    return f"[{num}] {head[2]}", body, label, bool(status and status[1] == "done")


def same(a: str, b: str) -> bool:
    """GitHub may store CRLF and trims the ends of a body."""
    return a.replace("\r\n", "\n").strip() == b.strip()


def main(root: Path, create: bool, update: bool) -> None:
    files = sorted(p for p in root.rglob("[0-9][0-9]-*.md") if re.match(r"# \d+: ", p.read_text()))
    issues = json.loads(gh("issue", "list", "--state", "all", "--limit", "1000", "--json", "number,title,body"))
    existing = {i["title"]: i for i in issues}
    made = 0
    for path in files:
        title, body, label, done = read(path)
        old = existing.get(title)
        if old and same(old["body"], body):
            continue
        if old:
            print(f"{'rewrite' if update else 'differs'} {title}")
            if update:
                gh("issue", "edit", str(old["number"]), "--body", body)
            continue
        print(f"{'create' if create else 'would create'} {title}")
        if not create:
            continue
        args = ["issue", "create", "--title", title, "--body", body]
        if label:
            gh("label", "create", label, "--force", "--color", "5319e7")
            args += ["--label", label]
        url = gh(*args).strip()
        if done:
            gh("issue", "close", url, "--reason", "completed")
        made += 1
        time.sleep(1)  # stay under GitHub's secondary rate limit for content creation
    print(f"{made} created" if create else "dry run: nothing created")


if __name__ == "__main__":
    assert same("a\r\nb\n", "a\nb") and not same("a", "b")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp, "Epic_10_Web_app", "07-a.md").resolve()
        f.parent.mkdir()
        f.write_text("# 07: A b\n\n**Status:** done\n")
        assert read(f)[0::2] == ("[10/07] A b", "Epic 10: Web app") and read(f)[3]
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve(), "--create" in sys.argv, "--update" in sys.argv)
