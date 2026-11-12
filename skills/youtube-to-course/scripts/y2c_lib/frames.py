"""Optional stage — keyframes at scene/slide changes (ffmpeg) + OCR (tesseract), for slides, code and whiteboards.

Costs bandwidth + CPU, no tokens. The LLM never sees images: only the OCR text, as `[on-screen]` lines inside segments
(so `segment` must run after `frames`). Frames live in work/vNN/frames/ for a human to inspect.
work/vNN/frames.json = [{"t": seconds, "text": "..."}]
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .common import Work, norm_ws, read_json, write_json
from .fetch import yt_dlp

MIN_WORDS = 4


def _ocr(img: Path, lang: str) -> str:
    p = subprocess.run(["tesseract", str(img), "stdout", "-l", lang, "--psm", "6"], capture_output=True, text=True)
    text = norm_ws(p.stdout)
    words = re.findall(r"\w{2,}", text)
    letters = sum(c.isalnum() for c in text)
    if len(words) < MIN_WORDS or letters < 0.6 * max(len(text), 1):   # garbage from faces/photos
        return ""
    return text[:400]


def _similar(a: str, b: str) -> bool:
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) > 0.8


def extract_frames(work: Work, threshold: float = 0.05, max_frames: int = 60, ocr: str = "auto", video_file: str | None = None) -> dict:
    ok = shutil.which("ffmpeg") and subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0
    if not ok:
        raise SystemExit("ffmpeg is missing or broken (e.g. dyld 'Library not loaded: libx265'): brew reinstall ffmpeg   "
                         "(frames are optional; the rest of the pipeline does not need ffmpeg)")
    have_ocr = ocr != "off" and shutil.which("tesseract") is not None
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout if have_ocr else ""
    summary = {}
    for v in read_json(work.videos)["videos"]:
        s, e = v["scope"]
        vd = work.vdir(v["id"])
        fdir = vd / "frames"
        shutil.rmtree(fdir, ignore_errors=True)
        fdir.mkdir(parents=True)
        lang = "eng"
        cues = vd / "cues.json"
        if cues.exists() and read_json(cues).get("language", "en").startswith("ru") and "rus" in langs:
            lang = "rus+eng"
        with tempfile.TemporaryDirectory() as t:
            vid = Path(t) / "v.mp4"
            if video_file:
                vid = Path(video_file)   # local file: its time 0 must be the video's time `s` (trim it, or use the full video with no --start)
            else:
                yt_dlp(["-f", "worst[height>=360]/worst", "--download-sections", f"*{s}-{e}", "--force-keyframes-at-cuts",
                        "--no-warnings", "--no-playlist", "-o", str(vid), f"https://www.youtube.com/watch?v={v['yt_id']}"])
            if not vid.exists():
                vid = list(Path(t).glob("v.*"))[0]
            vf = f"select='eq(n,0)+gt(scene,{threshold})',showinfo"
            for flag in ("-fps_mode", "-vsync"):   # ffmpeg >= 5.1 wants -fps_mode, older builds only know -vsync
                p = subprocess.run(["ffmpeg", "-loglevel", "info", "-y", "-i", str(vid), "-vf", vf, flag, "vfr", "-q:v", "4",
                                    str(fdir / "f%04d.jpg")], capture_output=True, text=True)
                if "Unrecognized option" not in p.stderr:
                    break
            if p.returncode != 0:
                raise SystemExit(f"ffmpeg failed on {v['id']}: {p.stderr.strip()[-400:]}")
        times = [float(m.group(1)) + s for m in re.finditer(r"pts_time:([\d.]+)", p.stderr)]
        imgs = sorted(fdir.glob("f*.jpg"))
        items, last = [], ""
        step = max(1, len(imgs) // max_frames)
        for img, tm in list(zip(imgs, times))[::step]:
            text = _ocr(img, lang) if have_ocr else ""
            if text and not _similar(text, last):
                items.append({"t": int(tm), "text": text, "frame": img.name})
                last = text
        write_json(vd / "frames.json", items)
        summary[v["id"]] = {"scene_changes": len(imgs), "frames_with_text": len(items), "ocr": have_ocr}
    return summary
