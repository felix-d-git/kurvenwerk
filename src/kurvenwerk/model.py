"""Datenmodell: Projekt → Seiten → Tabellen → Spalten, gespeichert als JSON."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = 1
ROLES = ("X", "Y", "Δx", "Δy")


@dataclass
class Column:
    name: str = ""
    unit: str = ""
    role: str = "Y"
    values: list[float | None] = field(default_factory=list)  # None = leere Zelle

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


@dataclass
class Project:
    pages: list[Page] = field(default_factory=lambda: [Page()])

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
            ], p.get("show_plot", True))
            for p in d["pages"]
        ])

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
