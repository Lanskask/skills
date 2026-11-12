import copy

from conftest import lesson, save_lesson, write_outline
from y2c_lib.validate import status, validate_course, validate_lesson, validate_outline


def errs(r):
    return " | ".join(r.errors)


def test_good_course_passes(work):
    write_outline(work)
    save_lesson(work, lesson())
    save_lesson(work, lesson("L-02", "s002", (305, 340), quote="Each step assigns charge to the grid then solves the field"))
    res = validate_course(work)
    assert not any(r.errors for r in res), [errs(r) for r in res]


def test_coverage_error_when_segment_unused(work):
    write_outline(work, [{"id": "L-01", "title": "Screening", "objectives": ["Explain the Debye length", "Describe quasi neutrality"],
                          "source_refs": [{"segment": "s001"}]}])
    assert "coverage: s002" in errs(validate_outline(work))


def test_fake_quote_rejected(work):
    write_outline(work)
    save_lesson(work, lesson(quote="Plasma is a mysterious fifth force that nobody understands"))
    assert "quote matches the transcript" in errs(validate_lesson(work, "L-01"))


def test_quote_must_be_near_its_timestamp(work):
    write_outline(work)
    save_lesson(work, lesson(quote="The Debye length is the distance over which a charge is screened", at=560))
    assert "quote matches" in errs(validate_lesson(work, "L-01"))


def test_quote_over_25_words(work):
    write_outline(work)
    long = " ".join(["Debye"] * 26)
    save_lesson(work, lesson(quote=long))
    assert "max 25" in errs(validate_lesson(work, "L-01"))


def test_timestamp_beyond_video_and_in_other_segment(work):
    write_outline(work)
    d = lesson()
    d["screens"][1]["blocks"][0]["cite"] = [9999]
    save_lesson(work, d)
    assert "beyond the video" in errs(validate_lesson(work, "L-01"))
    d = lesson()
    d["screens"][1]["blocks"][0]["cite"] = [400]
    save_lesson(work, d)
    r = validate_lesson(work, "L-01")
    assert any("another segment" in w for w in r.warnings) and not r.errors


def test_long_copy_outside_quote_rejected(work):
    write_outline(work)
    d = lesson()
    d["screens"][0]["blocks"][0]["text"] = ("A plasma is an ionized gas where charges move freely. The Debye length is the distance over which "
                                            "a charge is screened. Beyond the Debye length the plasma looks neutral [[Debye length]]")
    save_lesson(work, d)
    assert "copied from the transcript" in errs(validate_lesson(work, "L-01"))


def test_structure_rules(work):
    write_outline(work)
    d = lesson()
    d["screens"][0]["covers"] = [0, 5]
    d["glossary"] = d["glossary"][:1]                      # [[plasma]] now undefined
    d["quiz"][0]["answer"] = 7
    d["sources"]["segments"] = ["s002"]
    save_lesson(work, d)
    e = errs(validate_lesson(work, "L-01"))
    for needle in ("covers index 5", "no glossary entry", "answer index", "sources.segments"):
        assert needle in e


def test_schema_rejects_page_style_citation(work):
    write_outline(work)
    d = copy.deepcopy(lesson())
    d["screens"][1]["blocks"][0]["cite"] = ["p.4"]
    save_lesson(work, d)
    assert "list of whole seconds" in errs(validate_lesson(work, "L-01"))


def test_module_must_not_mix_videos(work):
    from y2c_lib.common import read_json, write_json
    m = read_json(work.manifest)
    m["videos"].append(dict(m["videos"][0], id="v02"))
    m["segments"][1]["video"] = "v02"
    write_json(work.manifest, m)
    write_outline(work)
    assert "one video per module" in errs(validate_outline(work)) and "v02 has no module" in errs(validate_outline(work))


def test_status_and_render(work, tmp_path):
    from y2c_lib.render import render
    write_outline(work)
    save_lesson(work, lesson())
    assert "L-01: validated" in status(work) and "L-02: todo" in status(work)
    out = render(work, work.out, partial=True)
    html = (work.out / "index.html").read_text()
    assert out["lessons"] == 1 and "https://youtu.be/abcdefghijk?t=10" in html and "Debye length" in html
    assert "COURSE_TITLE" not in html and "NAV_DOTS" not in html
