import json

import pytest

from kurvenwerk.model import VERSION, Column, Page, Project, Table


def sample() -> Project:
    t = Table("Kennlinie", [
        Column("U", "mV", "X", [0.0, 1.5, None, 3.25]),
        Column("I", "µA", "Y", [0.1, 2.0, 2.9, 4.0], style={"color": "#ff0000", "axis": "y2"}),
        Column("ΔI", "µA", "Δy", [0.05, 0.05, 0.05, 0.05]),
    ])
    return Project([Page("Aufgabe 1", [t, Table()], plot={"title": "$I(U)$", "xlog": True}),
                    Page("Aufgabe 2", [], show_plot=False)], style={"marker": "s"})


def test_roundtrip(tmp_path):
    p = sample()
    f = tmp_path / "a.kwproj"
    p.save(f)
    assert Project.load(f) == p
    raw = json.loads(f.read_text(encoding="utf-8"))
    assert raw["version"] == VERSION
    assert raw["pages"][0]["tables"][0]["columns"][0]["values"] == [0.0, 1.5, None, 3.25]
    assert "µA" in f.read_text(encoding="utf-8")  # Einheiten unverfälscht


def test_rejects_newer_version():
    with pytest.raises(ValueError):
        Project.from_dict({"version": VERSION + 1, "pages": []})


def test_rejects_unknown_role():
    with pytest.raises(ValueError):
        Column("x", "", "Z")
