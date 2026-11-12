# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""youtube-to-course CLI. Every command is deterministic and makes no LLM calls.

  prepare   URL --out DIR [--start T --end T] [--items 1-5] [--max-videos N] [--lang xx] [--whisper auto|off|force] [--model small] [--frames]
            = fetch + transcript + clean + segment + digest in one go (resumable per stage)
  fetch | transcript | clean | segment | digest | frames        individual stages (re-runs, debugging)
  select    --out DIR [--lesson L-01] [--budget 2500]           Pass-2 transcript pack(s)
  read      --out DIR --segment s003 [--from 90 --to 240]       explicit full-text fallback (logged)
  validate  --out DIR [--stage outline|lesson|course] [--lesson L-01]
  render    --out DIR [--partial]                               drafts -> HTML course (+ index.html)
  status    --out DIR                                           what is done / what is next (resumability)
Times: seconds, M:SS, H:MM:SS or 1h2m3s.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from y2c_lib.common import Work, parse_time, read_json  # noqa: E402


def _work(a) -> Work:
    return Work(Path(a.out))


def cmd_fetch(a) -> None:
    from y2c_lib.fetch import fetch
    d = fetch(_work(a), a.url, parse_time(a.start) if a.start else None, parse_time(a.end) if a.end else None, a.items, a.max_videos)
    for v in d["videos"]:
        print(f"{v['id']}  {v['yt_id']}  {v['duration']}s  chapters={len(v['chapters'])}  manual={v['has_manual_subs'][:4]}  "
              f"auto={v['has_auto_subs'][:3]}  scope={v['scope']}  {v['title']}")


def cmd_transcript(a) -> None:
    from y2c_lib.transcript import get_transcript
    w = _work(a)
    for v in read_json(w.videos)["videos"]:
        print(v["id"], get_transcript(w, v["id"], a.whisper, a.model, a.lang, a.audio_file))


def cmd_clean(a) -> None:
    from y2c_lib.clean import clean
    w = _work(a)
    for v in read_json(w.videos)["videos"]:
        r = clean(w, v["id"], a.keep_sponsors)
        print(v["id"], f"words {r['words_raw']} -> {r['words_clean']}, lines {r['lines']}, sponsor runs removed {len(r['sponsor_runs_removed'])}")


def cmd_segment(a) -> None:
    from y2c_lib.segment import segment_all
    m = segment_all(_work(a))
    for s in m["segments"]:
        print(f"{s['id']}  {s['video']}  {s['start']:>5}-{s['end']:<5}  {s['words']:>5}w  {s['split']:<7} {s['kind']:<7} {s['title'][:60]}")


def cmd_digest(a) -> None:
    from y2c_lib.digest import digest_all
    print(digest_all(_work(a)))


def cmd_frames(a) -> None:
    from y2c_lib.frames import extract_frames
    print(extract_frames(_work(a), a.threshold, a.max_frames, a.ocr, a.video_file))


def cmd_prepare(a) -> None:
    w = _work(a)
    cmd_fetch(a)
    cmd_transcript(a)
    cmd_clean(a)
    if a.frames:
        cmd_frames(a)
    cmd_segment(a)
    cmd_digest(a)
    m = read_json(w.manifest)
    words = sum(s["words"] for s in m["segments"])
    print(f"\nprepared: {len(m['videos'])} video(s), {len(m['segments'])} segments, {words} words. Next: read {w.digest} (Pass 1) and write {w.outline}")


def cmd_select(a) -> None:
    from y2c_lib.select import pack
    w = _work(a)
    ids = [a.lesson] if a.lesson else [l["id"] for m in read_json(w.outline)["modules"] for l in m["lessons"]]
    for lid in ids:
        print(pack(w, lid, a.budget))


def cmd_read(a) -> None:
    from y2c_lib.select import read_range
    print(read_range(_work(a), a.segment, parse_time(a.__dict__["from"]) if a.__dict__["from"] else None,
                     parse_time(a.to) if a.to else None, a.max_tokens))


def cmd_validate(a) -> None:
    from y2c_lib.validate import run_validate
    sys.exit(run_validate(_work(a), a.stage, a.lesson))


def cmd_render(a) -> None:
    from y2c_lib.render import render
    print(json.dumps(render(_work(a), Path(a.out), a.partial), indent=2))


def cmd_status(a) -> None:
    from y2c_lib.validate import status
    print(status(_work(a)))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, url=False, **kw):
        q = sp.add_parser(name, **kw)
        q.add_argument("--out", required=True)
        if url:
            q.add_argument("url")
            q.add_argument("--start")
            q.add_argument("--end")
            q.add_argument("--items", help="playlist items, e.g. 1-5,8")
            q.add_argument("--max-videos", type=int)
        q.set_defaults(fn=fn)
        return q

    def opts(q):
        q.add_argument("--lang")
        q.add_argument("--whisper", choices=["auto", "off", "force"], default="auto")
        q.add_argument("--model", default="small", help="faster-whisper model: tiny|base|small|medium|large-v3")
        q.add_argument("--keep-sponsors", action="store_true")
        q.add_argument("--frames", action="store_true")
        q.add_argument("--audio-file", help="local audio for Whisper (single video; skips the YouTube audio download)")
        q.add_argument("--video-file", help="local video for --frames (single video)")
        q.add_argument("--threshold", type=float, default=0.05)
        q.add_argument("--max-frames", type=int, default=60)
        q.add_argument("--ocr", choices=["auto", "off"], default="auto")

    opts(add("prepare", cmd_prepare, url=True))
    add("fetch", cmd_fetch, url=True)
    q = add("transcript", cmd_transcript)
    opts(q)
    q = add("clean", cmd_clean)
    q.add_argument("--keep-sponsors", action="store_true")
    add("segment", cmd_segment)
    add("digest", cmd_digest)
    q = add("frames", cmd_frames)
    q.add_argument("--video-file")
    q.add_argument("--threshold", type=float, default=0.05)
    q.add_argument("--max-frames", type=int, default=60)
    q.add_argument("--ocr", choices=["auto", "off"], default="auto")
    q = add("select", cmd_select)
    q.add_argument("--lesson")
    q.add_argument("--budget", type=int, default=2500)
    q = add("read", cmd_read)
    q.add_argument("--segment", required=True)
    q.add_argument("--from")
    q.add_argument("--to")
    q.add_argument("--max-tokens", type=int, default=4000)
    q = add("validate", cmd_validate)
    q.add_argument("--stage", choices=["outline", "lesson", "course"], default="course")
    q.add_argument("--lesson")
    q = add("render", cmd_render)
    q.add_argument("--partial", action="store_true")
    add("status", cmd_status)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
