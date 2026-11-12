"""Stage 1 — fetch metadata with yt-dlp (no download of media). Records the scope (video / playlist / time range).

work/videos.json = {"scope": {...}, "videos": [{"id": "v01", "yt_id", "title", "duration", "chapters", ...}]}
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess

from .common import Work, write_json

ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([\w-]{11})")


def yt_dlp(args: list[str]) -> str:
    exe = shutil.which("yt-dlp")
    if not exe:
        raise SystemExit("yt-dlp not found: brew install yt-dlp (or pipx install yt-dlp)")
    extra = shlex.split(os.environ.get("Y2C_YTDLP_ARGS", ""))   # e.g. "--cookies-from-browser chrome" when YouTube answers 403
    p = subprocess.run([exe, *extra, *args], capture_output=True, text=True)
    if p.returncode != 0:
        hint = ("\nHint: YouTube refused the media download (403). Pass a local file with --audio-file/--video-file, or set "
                "Y2C_YTDLP_ARGS (e.g. '--cookies-from-browser chrome'). Captions and metadata do not need this.") if "403" in p.stderr else ""
        raise SystemExit(f"yt-dlp failed: {p.stderr.strip()[-600:]}{hint}")
    return p.stdout


def _video_meta(info: dict, vid: str) -> dict:
    chapters = [{"title": c.get("title", ""), "start": int(c["start_time"]), "end": int(c["end_time"])}
                for c in (info.get("chapters") or [])]
    return {
        "id": vid, "yt_id": info["id"], "title": info.get("title", ""), "channel": info.get("channel") or info.get("uploader", ""),
        "duration": int(info.get("duration") or 0), "upload_date": info.get("upload_date", ""),
        "description": (info.get("description") or "")[:4000], "chapters": chapters,
        "url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={info['id']}",
        "language": info.get("language"), "license": info.get("license"),
        "has_manual_subs": sorted((info.get("subtitles") or {}).keys()),
        "has_auto_subs": sorted(k for k in (info.get("automatic_captions") or {}) if k.endswith("-orig") or k in ("en", "ru")),
    }


def fetch(work: Work, url: str, start: int | None = None, end: int | None = None,
          items: str | None = None, max_videos: int | None = None) -> dict:
    """`url` may be a video, a playlist, or an 11-char video id. `start`/`end` (seconds) apply to a single video only."""
    if re.fullmatch(r"[\w-]{11}", url):
        url = f"https://www.youtube.com/watch?v={url}"
    flat = json.loads(yt_dlp(["--flat-playlist", "--dump-single-json", "--no-warnings", url] + (["--playlist-items", items] if items else [])))
    entries = flat.get("entries")
    if entries is not None:  # playlist
        if start is not None or end is not None:
            raise SystemExit("--start/--end apply to a single video, not a playlist")
        ids = [e["id"] for e in entries if e and e.get("id")][: max_videos or None]
        kind, title = "playlist", flat.get("title", "")
    else:
        ids, kind, title = [flat["id"]], "video", flat.get("title", "")
    videos = []
    for n, yid in enumerate(ids, start=1):
        info = json.loads(yt_dlp(["--dump-single-json", "--skip-download", "--no-warnings", "--no-playlist",
                                  f"https://www.youtube.com/watch?v={yid}"]))
        videos.append(_video_meta(info, f"v{n:02d}"))
    if kind == "video" and (start is not None or end is not None):
        v = videos[0]
        s, e = start or 0, min(end if end is not None else v["duration"], v["duration"])
        if not 0 <= s < e:
            raise SystemExit(f"bad time range {s}-{e} (video is {v['duration']}s)")
        v["scope"] = [s, e]
    for v in videos:
        v.setdefault("scope", [0, v["duration"]])
    data = {"scope": {"kind": kind, "url": url, "title": title, "items": items}, "videos": videos}
    work.mkdirs()
    write_json(work.videos, data)
    for v in videos:
        work.vdir(v["id"]).mkdir(parents=True, exist_ok=True)
    return data
