"""Datenmodell: Projekt → Seiten → Tabellen → Spalten, gespeichert als JSON."""
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = 6  # 2: Column.formula/gauss, 3: Column.style, Page.plot, Project.style, 4: Column.fit, 5: Page.description,
# 6: Unsicherheit u_x statt Δx (Rollen, Spaltennamen, Formeln)
ROLES = ("X", "Y", "u_x", "u_y")
U = "u_"  # Präfix der Unsicherheitsspalte: u_<Name>


@dataclass
class Column:
    name: str = ""
    unit: str = ""
    role: str = "Y"
    values: list[float | None] = field(default_factory=list)  # None = leere Zelle
    formula: str = ""  # berechnete Spalte, siehe formula.recompute
    gauss: bool = False  # Gauß-Fehler der Formel nach u_<name>
    style: dict = field(default_factory=dict)  # Reihen-Stil, Schlüssel siehe plot.SERIES
    fit: dict = field(default_factory=dict)  # Fit der Y-Spalte, Schlüssel siehe fit.FIT

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"Unbekannte Spaltenrolle: {self.role!r}")


def _migrate(c: dict) -> dict:
    """Spalte aus Version < 6: Δx/Δy → u_x/u_y, ΔU → u_U in Namen und Formeln."""
    c = dict(c)
    c["role"] = {"Δx": "u_x", "Δy": "u_y"}.get(c.get("role", "Y"), c.get("role", "Y"))
    c["name"] = re.sub(r"^Δ", U, c.get("name", ""))
    c["formula"] = re.sub(r"Δ(?=[^\W\d])", U, c.get("formula", ""))
    return c


@dataclass
class Table:
    name: str = "Tabelle 1"
    columns: list[Column] = field(default_factory=lambda: [Column("x", "", "X"), Column("y", "", "Y")])


@dataclass
class Page:
    title: str = "Seite 1"
    tables: list[Table] = field(default_factory=lambda: [Table()])
    show_plot: bool = True
    plot: dict = field(default_factory=dict)  # Achsen/Beschriftung, Schlüssel siehe plot.PLOT
    description: str = ""  # Freitext zur Seite


@dataclass
class Project:
    pages: list[Page] = field(default_factory=lambda: [Page()])
    style: dict = field(default_factory=dict)  # projektweiter Plot-Stil, Schlüssel siehe plot.STYLE

    def to_dict(self) -> dict:
        return {"version": VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        v = d.get("version")
        if not isinstance(v, int) or v > VERSION:
            raise ValueError(f"Projektversion {v!r} wird nicht unterstützt (max. {VERSION})")
        return cls([
            Page(p["title"], [
                Table(t["name"], [Column(**(c if v >= 6 else _migrate(c))) for c in t["columns"]]) for t in p["tables"]
            ], p.get("show_plot", True), p.get("plot", {}), p.get("description", ""))
            for p in d["pages"]
        ], d.get("style", {}))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
