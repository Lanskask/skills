import json

from conftest import make_cues
from y2c_lib.clean import drop_sponsors, merge
from y2c_lib.common import fmt_time, parse_time, read_json
from y2c_lib.select import pack, read_range
from y2c_lib.transcript import parse_json3


def test_time_helpers():
    assert parse_time("1:02:03") == 3723 and parse_time("1h2m3s") == 3723 and parse_time("90") == 90
    assert fmt_time(3725) == "1:02:05" and fmt_time(75) == "1:15"


def test_rolling_duplicates_and_noise_removed():
    cues = [{"start": 0, "end": 2, "text": "so today we talk about [Music] plasma"},
            {"start": 2, "end": 4, "text": "we talk about plasma and um its screening"},
            {"start": 4, "end": 6, "text": "and its screening length. Next point here."}]
    text = " ".join(ln["text"] for ln in merge(cues))
    assert text.lower().count("screening") == 1 and "[Music]" not in text and " um " not in text
    assert text.startswith("so today we talk about plasma and")


def test_lines_keep_timestamps_monotonic():
    lines = merge(make_cues("word " * 200, 5))
    starts = [ln["start"] for ln in lines]
    assert starts == sorted(starts) and starts[0] >= 5 and all(len(ln["text"].split()) <= 28 for ln in lines)


def test_sponsor_run_dropped_and_reported():
    lines = [{"start": i * 5.0, "end": i * 5.0 + 5, "text": t} for i, t in enumerate(
        ["real content about plasma.", "This video is sponsored by Acme, use the promo code PLASMA.", "Click the link in the description for a free trial.",
         "now back to physics.", "more physics here."])]
    kept, removed = drop_sponsors(lines)
    assert len(removed) == 1 and all("sponsor" not in k["text"] for k in kept) and len(kept) == 3


def test_parse_json3(tmp_path):
    p = tmp_path / "x.json3"
    p.write_text(json.dumps({"events": [{"tStartMs": 1500, "dDurationMs": 2000, "segs": [{"utf8": "hello "}, {"utf8": "world"}]},
                                        {"tStartMs": 4000, "segs": [{"utf8": "\n"}]}, {"dDurationMs": 5}]}))
    assert parse_json3(p) == [{"start": 1.5, "end": 3.5, "text": "hello world"}]


def test_segments_follow_chapters(work):
    m = read_json(work.manifest)
    assert [s["split"] for s in m["segments"]] == ["chapter", "chapter"]
    s1, s2 = m["segments"]
    assert s1["id"] == "s001" and s1["start"] < 10 and 150 <= s1["end"] <= 215 and 295 <= s2["start"] <= 310 and s1["kind"] == "content"
    assert (work.root / "segments" / "s001.md").read_text().startswith("<!-- segment s001 · v01 ·")


def test_topic_split_without_chapters(work):
    from y2c_lib.segment import segment_video
    meta = read_json(work.videos)["videos"][0] | {"chapters": []}
    lines = read_json(work.vdir("v01") / "cues.json")["lines"]
    segs = segment_video(meta, lines, "en")
    assert len(segs) >= 2 and all(s["source"] == "topic" for s in segs)
    cut = segs[0]["lines"][-1]["end"]
    assert 150 <= cut <= 350           # the boundary lands near the real topic change at 300 s


def test_digest_is_small_and_has_terms(work):
    d = work.digest.read_text()
    assert "### s001" in d and "### s002" in d and "Debye" in d and len(d) < 4000


def test_deterministic(work, tmp_path):
    first = work.digest.read_text()
    from y2c_lib.digest import digest_all
    digest_all(work)
    assert work.digest.read_text() == first


def test_pack_complete_and_trimmed(work):
    from conftest import write_outline
    write_outline(work)
    r = pack(work, "L-01", budget=2500)
    assert r["complete"] and "|" in (work.selections / "L-01.md").read_text()
    r = pack(work, "L-01", budget=60)
    assert not r["complete"] and "omitted" in (work.selections / "L-01.md").read_text()
    assert "[0:" in read_range(work, "s001", 0, 20)


def test_digest_works_without_punctuation(work):
    """Auto-captions have no sentence punctuation; the digest must still produce key lines (regression)."""
    from y2c_lib.common import read_json, write_json
    from y2c_lib.digest import digest_all
    d = read_json(work.vdir("v01") / "cues.json")
    for ln in d["lines"]:
        ln["text"] = ln["text"].replace(".", "").replace(",", "").lower()
    write_json(work.vdir("v01") / "cues.json", d)
    from y2c_lib.segment import segment_all
    segment_all(work)
    digest_all(work)
    assert work.digest.read_text().count("- key [") >= 4


def test_on_screen_text_is_merged_into_segments_and_digest(work):
    from y2c_lib.common import write_json
    from y2c_lib.digest import digest_all
    from y2c_lib.segment import segment_all
    write_json(work.vdir("v01") / "frames.json", [{"t": 20, "text": "Debye length lambda D equals sqrt of eps0 kB Te over n e squared", "frame": "f1.jpg"}])
    segment_all(work)
    seg = (work.root / "segments" / "s001.md").read_text()
    assert "[on-screen] Debye length lambda D" in seg and "|20]" in seg
    digest_all(work)
    assert "- on-screen [0:20]: Debye length lambda D" in work.digest.read_text()
