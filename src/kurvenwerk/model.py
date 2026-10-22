"""Datenmodell: Projekt → Seiten → Tabellen → Spalten, gespeichert als JSON."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = 3  # 2: Column.formula/gauss, 3: Column.style, Page.plot, Project.style
ROLES = ("X", "Y", "Δx", "Δy")


@dataclass
class Column:
    name: str = ""
    unit: str = ""
    role: str = "Y"
    values: list[float | None] = field(default_factory=list)  # None = leere Zelle
    formula: str = ""  # berechnete Spalte, siehe formula.recompute
    gauss: bool = False  # Gauß-Fehler der Formel nach Δ<name>
    style: dict = field(default_factory=dict)  # Reihen-Stil, Schlüssel siehe plot.SERIES

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"Unbekannte Spaltenrolle: {self.role!r}")


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
                Table(t["name"], [Column(**c) for c in t["columns"]]) for t in p["tables"]
            ], p.get("show_plot", True), p.get("plot", {}))
            for p in d["pages"]
        ], d.get("style", {}))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
