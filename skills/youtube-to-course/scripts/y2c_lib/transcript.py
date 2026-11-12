"""Stage 2 — transcript, in this order: manual captions -> auto captions -> local Whisper (opt-out with --no-whisper).

Writes work/vNN/cues_raw.json = {"source": manual|auto|whisper, "language", "cues": [{"start","end","text"}]}
Cues are only restricted to the requested time range here; cleaning happens in clean.py.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .common import Work, read_json, write_json
from .fetch import yt_dlp

WORKER = Path(__file__).resolve().parents[1] / "whisper_worker.py"


def _pick_lang(avail: list[str], want: str | None) -> str | None:
    if not avail:
        return None
    for cand in (want, "en", "ru"):
        if cand and cand in avail:
            return cand
    return sorted(avail)[0]


def parse_json3(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cues = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs or "tStartMs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        start = ev["tStartMs"] / 1000
        cues.append({"start": round(start, 2), "end": round(start + ev.get("dDurationMs", 0) / 1000, 2), "text": text})
    return cues


def _download_subs(yt_id: str, lang: str, auto: bool, tmp: Path) -> list[dict]:
    flag = "--write-auto-subs" if auto else "--write-subs"
    yt_dlp([flag, "--skip-download", "--sub-langs", lang, "--sub-format", "json3", "--no-warnings", "--no-playlist",
            "-o", str(tmp / "%(id)s"), f"https://www.youtube.com/watch?v={yt_id}"])
    files = sorted(tmp.glob(f"{yt_id}*.json3"))
    return parse_json3(files[0]) if files else []


def _whisper(meta: dict, model: str, lang: str | None, tmp: Path, audio_file: str | None = None) -> dict:
    """Audio is downloaded as-is (no ffmpeg needed: faster-whisper decodes it with PyAV) and only the scope range is transcribed."""
    s, e = meta["scope"]
    if audio_file:
        audio = Path(audio_file)
    else:
        yt_dlp(["-f", "bestaudio[abr<=64]/bestaudio", "--no-warnings", "--no-playlist", "-o", str(tmp / "raw.%(ext)s"),
                f"https://www.youtube.com/watch?v={meta['yt_id']}"])
        audio = next(tmp.glob("raw.*"))
    out = tmp / "whisper.json"
    full = (s, e) == (0, meta["duration"])
    p = subprocess.run(["uv", "run", str(WORKER), str(audio), str(out), model, lang or "auto"] + ([] if full else [str(s), str(e)]),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"whisper failed: {p.stderr.strip()[-500:]}")
    d = json.loads(out.read_text(encoding="utf-8"))
    return {"language": d["language"], "cues": d["cues"]}


def get_transcript(work: Work, vid: str, whisper: str = "auto", model: str = "small", lang: str | None = None,
                   audio_file: str | None = None) -> dict:
    """whisper: 'auto' (only if no captions), 'force' (skip captions), 'off'."""
    meta = next(v for v in read_json(work.videos)["videos"] if v["id"] == vid)
    s, e = meta["scope"]
    result = None
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        if whisper != "force":
            for auto in (False, True):
                avail = meta["has_auto_subs"] if auto else meta["has_manual_subs"]
                lg = _pick_lang(avail, lang or meta.get("language"))
                if not lg:
                    continue
                try:
                    cues = _download_subs(meta["yt_id"], lg, auto, tmp)
                except SystemExit:
                    cues = []
                if cues:
                    result = {"source": "auto" if auto else "manual", "language": lg, "cues": cues}
                    break
        if result is None and whisper != "off":
            w = _whisper(meta, model, lang, tmp, audio_file)
            result = {"source": "whisper", "model": model, **w}
    if result is None:
        raise SystemExit(f"{vid}: no captions and Whisper is off; re-run without --whisper off (or give captions)")
    result["cues"] = [c for c in result["cues"] if c["end"] > s and c["start"] < e]
    write_json(work.vdir(vid) / "cues_raw.json", result)
    return {"source": result["source"], "cues": len(result["cues"]), "language": result["language"]}
