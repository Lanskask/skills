import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from y2c_lib.clean import clean  # noqa: E402
from y2c_lib.common import Work, write_json  # noqa: E402
from y2c_lib.digest import digest_all  # noqa: E402
from y2c_lib.segment import segment_all  # noqa: E402

A = ("A plasma is an ionized gas where charges move freely. The Debye length is the distance over which a charge is screened. "
     "Beyond the Debye length the plasma looks neutral, which physicists call quasi neutrality. Electrons are light and fast "
     "so they screen charges quickly. Ions are heavy and slow so they barely move on that time scale. ") * 4
B = ("A particle in cell code follows many macro particles on a grid. Each step assigns charge to the grid then solves the field. "
     "The field is interpolated back to the particles and they are pushed forward in time. This loop repeats for every time step. "
     "The grid spacing must resolve the Debye length or the simulation heats up numerically. ") * 4


def make_cues(text: str, t0: float, step: float = 4.0) -> list[dict]:
    words, cues, t = text.split(), [], t0
    for i in range(0, len(words), 9):
        chunk = " ".join(words[i:i + 9])
        cues.append({"start": t, "end": t + step, "text": chunk})
        t += step
    return cues


@pytest.fixture
def work(tmp_path) -> Work:
    w = Work(tmp_path / "course")
    w.mkdirs()
    cues_a, cues_b = make_cues(A * 2, 0), make_cues(B * 2, 300)
    meta = {"id": "v01", "yt_id": "abcdefghijk", "title": "Plasma basics", "channel": "Dr Test", "duration": 600, "upload_date": "20260101",
            "description": "Debye length and particle in cell", "chapters": [{"title": "Plasma", "start": 0, "end": 300},
                                                                       {"title": "PIC", "start": 300, "end": 600}],
            "url": "u", "language": "en", "license": None, "has_manual_subs": ["en"], "has_auto_subs": [], "scope": [0, 600]}
    write_json(w.videos, {"scope": {"kind": "video", "url": "u", "title": "Plasma basics", "items": None}, "videos": [meta]})
    w.vdir("v01").mkdir()
    write_json(w.vdir("v01") / "cues_raw.json", {"source": "manual", "language": "en", "cues": cues_a + cues_b})
    clean(w, "v01")
    segment_all(w)
    digest_all(w)
    return w


def write_outline(w: Work, lessons=None) -> None:
    lessons = lessons or [
        {"id": "L-01", "title": "Screening", "objectives": ["Explain the Debye length", "Describe quasi neutrality in plain words"],
         "source_refs": [{"segment": "s001", "keywords": ["Debye"]}]},
        {"id": "L-02", "title": "The PIC loop", "objectives": ["Explain the four steps of the loop", "Apply the grid spacing rule"],
         "source_refs": [{"segment": "s002"}]}]
    write_json(w.outline, {"course": {"title": "Plasma", "lang": "en"}, "modules": [
        {"id": "M1", "video": "v01", "title": "Plasma basics", "subtitle": "From screening to simulation", "lessons": lessons}], "skipped": []})


def lesson(lid="L-01", seg="s001", t=(10, 40), quote="The Debye length is the distance over which a charge is screened", at=None):
    q = {"type": "quote", "text": quote, "at": at if at is not None else t[0], "meaning": "Charges are hidden beyond a certain distance."}
    return {"id": lid, "title": "Screening", "metaphor": "A crowd muffles one shout from far away.", "hook": "Why does a plasma look neutral?",
            "why_care": "You can estimate the grid size of a simulation before you run it, and you can explain to a colleague why the box looks neutral.",
            "screens": [
                {"id": "s1", "heading": "Screening", "covers": [0], "blocks": [
                    {"type": "text", "text": "A [[Debye length]] says how far a charge is felt in a plasma. Closer than that distance you see individual charges, "
                     "and farther away the surrounding electrons have hidden it. This hiding is called screening and it is why a hot gas of charges can conduct "
                     "electricity and still carry no net charge when you look at a large enough box.", "cite": [t[0]]}, q]},
                {"id": "s2", "heading": "Neutral at large scale", "covers": [1], "blocks": [
                    {"type": "callout", "variant": "info", "title": "Neutrality", "text": "Beyond that distance the [[plasma]] looks neutral.", "cite": [t[1]]}]}],
            "quiz": [{"question": "A plasma has a Debye length of 1 mm. What does a 1 m box look like?", "options": ["Neutral", "Charged", "Empty"],
                      "answer": 0, "explain_right": "Far larger than the Debye length.", "explain_wrong": "Screening makes it neutral.", "cite": [t[0]]}],
            "glossary": [{"term": "Debye length", "definition": "The distance over which a charge is screened by the plasma.", "cite": [t[0]]},
                         {"term": "plasma", "definition": "An ionized gas whose charges move freely.", "cite": [t[0]]}],
            "key_takeaways": ["Charges are screened.", "Plasmas look neutral at large scale."],
            "sources": {"segments": [seg], "read_full": []}}


def save_lesson(w: Work, d: dict) -> None:
    (w.drafts / f"{d['id']}.json").write_text(json.dumps(d), encoding="utf-8")
