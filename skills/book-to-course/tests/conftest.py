"""Shared fixtures: a synthetic en book (`pdf`) and a prepared course with the example outline + lessons (`course`)."""
from __future__ import annotations

import shutil

import pytest
from test_pipeline import EXAMPLE, make_pdf, prepare


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    return make_pdf("en", tmp_path_factory.mktemp("m") / "en.pdf")


@pytest.fixture()
def course(pdf, tmp_path):
    work, mf = prepare(pdf, tmp_path / "c")
    shutil.copy(EXAMPLE / "outline.json", work.outline)
    for f in EXAMPLE.glob("L-*.json"):
        shutil.copy(f, work.drafts / f.name)
    return work, mf
