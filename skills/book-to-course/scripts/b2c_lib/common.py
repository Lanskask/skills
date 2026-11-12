"""Shared helpers: paths, JSON IO, tokenisation, language detection, token estimates.

Everything here is deterministic: no randomness, no network, no LLM calls.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

# ── paths ────────────────────────────────────────────────────────────────


class Work:
    """Layout of the per-book work directory (`<out>/work`)."""

    def __init__(self, out: Path):
        self.out = Path(out)
        self.root = self.out / "work"
        self.pages = self.root / "pages"
        self.chapters = self.root / "chapters"
        self.digests = self.root / "digests"
        self.selections = self.root / "selections"
        self.drafts = self.root / "drafts"
        self.manifest = self.root / "manifest.json"
        self.structure = self.root / "structure.json"
        self.outline = self.root / "outline.json"
        self.report = self.root / "report.json"
        self.usage = self.root / "usage.jsonl"

    def mkdirs(self) -> None:
        for p in (self.pages, self.chapters, self.digests, self.selections, self.drafts):
            p.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def log_usage(work: Work, kind: str, label: str, text: str) -> None:
    """Append one line to usage.jsonl so token cost per step can be audited."""
    work.root.mkdir(parents=True, exist_ok=True)
    with work.usage.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, "label": label, "tokens": est_tokens(text)}) + "\n")


# ── text utilities ───────────────────────────────────────────────────────


def est_tokens(text: str) -> int:
    """Rough LLM token estimate: ~4 chars/token for Latin, ~2.5 for Cyrillic.

    Documented as an estimate; real tokenizers differ by model.
    """
    if not text:
        return 0
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    other = len(text) - cyr
    return math.ceil(other / 4 + cyr / 2.5)


def slugify(title: str, maxlen: int = 40) -> str:
    t = unicodedata.normalize("NFKD", title.lower())
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"[\s_-]+", "-", t).strip("-")
    return (t[:maxlen].rstrip("-")) or "untitled"


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def norm_for_match(s: str) -> str:
    """Normalise text for verbatim-quote matching (quotes, dashes, hyphens, case)."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("­", "")  # soft hyphen
    s = re.sub(r"[‘’‚‛`´]", "'", s)
    s = re.sub(r"[“”„«»]", '"', s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)  # de-hyphenation across line breaks
    s = re.sub(r"[^\w\s'\"%=+*/<>().,;:-]", "", s, flags=re.UNICODE)
    return norm_ws(s)


def parse_range(spec: str | None) -> tuple[int, int] | None:
    """'120-180' -> (120, 180); '7' -> (7, 7); None -> None."""
    if not spec:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*(?:[-–:]\s*(\d+))?\s*", spec)
    if not m:
        raise ValueError(f"bad range {spec!r}; use e.g. 120-180")
    a = int(m.group(1))
    b = int(m.group(2) or a)
    if b < a:
        raise ValueError(f"range end before start: {spec!r}")
    return a, b


# ── language, stopwords, tokens ──────────────────────────────────────────

STOP_EN = set(
    """a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her
here hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or
other our out over own same she should so some such than that the their them then there these they this those
through to too under until up very was we were what when where which while who whom why will with would you your
may might must shall one two three first second however thus therefore hence let see e.g i.e eq fig figure table
also given using used use""".split()
)
STOP_RU = set(
    """и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня
еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там
потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже
себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас
были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего
них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда
конечно всю между это также которые который которая которое которых которым рис табл""".split()
)


def detect_lang(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    return "ru" if cyr / len(letters) > 0.3 else "en"


_WORD = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)


def stem(tok: str, lang: str) -> str:
    """Very crude, deterministic stemmer. Good enough for ranking, not for display."""
    if lang == "ru":
        return tok[:6]
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokens(text: str, lang: str) -> list[str]:
    stop = STOP_RU if lang == "ru" else STOP_EN
    out = []
    for w in _WORD.findall(text.lower()):
        if len(w) < 3 or w in stop:
            continue
        out.append(stem(w, lang))
    return out


_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ\"«(\[])")


def sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(norm_ws(text))
    return [p for p in parts if p]


def truncate_words(text: str, n: int) -> str:
    w = text.split()
    return text if len(w) <= n else " ".join(w[:n]) + " …"
