"""Plot-Bereich einer Seite (Canvas + Werkzeugleiste) und die Dialoge für Achsen, Stil, Reihe, Export."""
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.colors import is_color_like
from matplotlib.figure import Figure
from PySide6.QtCore import QTimer
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QToolButton, QVBoxLayout, QWidget)

from . import plot
from .formula import FormulaError, number
from .model import Page, Project


class FormDialog(QDialog):
    """Formular aus (Schlüssel, Beschriftung, Art); Art: text, math, num (leer = auto), bool, color,
    colors oder ein Tupel Auswahlwerte. Prüft beim OK, Fehlertext unten, Dialog bleibt offen."""

    def __init__(self, title: str, spec: list, values: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.spec, self.w = spec, {}
        f = QFormLayout(self)
        for key, label, kind in spec:
            v = values.get(key)
            if kind == "bool":
                w = QCheckBox(checked=bool(v))
            elif isinstance(kind, tuple):
                w = QComboBox()  # nur Auswahl → kein ungültiger Marker/Linienstil
                w.addItems(kind)
                w.setCurrentText(str(v))
            else:
                w = QLineEdit("" if v is None else f"{v:g}" if isinstance(v, float) else str(v))
            if kind == "math":
                w.setPlaceholderText("auto · LaTeX-Mathe in $…$, z.B. $\\Delta U$ / mV")
            elif kind == "num":
                w.setPlaceholderText("auto")
            self.w[key] = w
            f.addRow(label, w)
        self.msg = QLabel(wordWrap=True)
        f.addRow(self.msg)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.check)
        b.rejected.connect(self.reject)
        f.addRow(b)
        self.result_values = {}

    def check(self):
        out = {}
        for key, label, kind in self.spec:
            w = self.w[key]
            if kind == "bool":
                out[key] = w.isChecked()
                continue
            t = (w.currentText() if isinstance(kind, tuple) else w.text()).strip()
            err = None
            if kind == "num":
                try:
                    t = number(t) if t else None
                except FormulaError as e:
                    err = str(e)
            elif kind == "math":
                err = plot.label_error(t)
            elif kind == "color" and t and not is_color_like(t):
                err = "keine Farbe (z.B. #1f77b4, red, C0)"
            elif kind == "colors" and not all(is_color_like(c.strip()) for c in t.split(",") if c.strip()):
                err = "Farben kommagetrennt, z.B. #1f77b4, red"
            if err:
                self.msg.setText(f"{label}: {err}")
                self.w[key].setFocus()
                return
            out[key] = t
        self.result_values = out
        self.accept()


def ask(title: str, spec: list, values: dict, parent=None) -> dict | None:
    d = FormDialog(title, spec, values, parent)
    return d.result_values if d.exec() else None


AXES_SPEC = [("title", "Titel", "math"), ("xlabel", "x-Achse", "math"), ("ylabel", "y-Achse", "math"),
             ("y2label", "2. y-Achse", "math"),
             ("xmin", "x min", "num"), ("xmax", "x max", "num"), ("ymin", "y min", "num"),
             ("ymax", "y max", "num"), ("y2min", "2. y min", "num"), ("y2max", "2. y max", "num"),
             ("xlog", "x logarithmisch", "bool"), ("ylog", "y logarithmisch", "bool"),
             ("y2log", "2. y logarithmisch", "bool"), ("legend", "Legende", "bool"),
             ("swap", "Achsen tauschen x↔y", "bool")]
STYLE_SPEC = [("marker", "Marker", plot.MARKERS), ("markersize", "Markergröße", "num"),
              ("linestyle", "Linie", plot.LINESTYLES), ("linewidth", "Linienbreite", "num"),
              ("capsize", "Fehlerbalken-Kappe", "num"), ("colors", "Farbfolge", "colors"),
              ("font", "Schrift", ("serif", "sans-serif", "monospace")), ("fontsize", "Schriftgröße (pt)", "num"),
              ("grid", "Gitter", "bool")]
SERIES_SPEC = [("label", "Legende", "math"), ("color", "Farbe", "color"),
               ("marker", "Marker", ("",) + plot.MARKERS), ("linestyle", "Linie", ("",) + plot.LINESTYLES),
               ("axis", "Achse", ("y", "y2"))]
EXPORT_SPEC = [("export_w", "Breite (cm)", "num"), ("export_h", "Höhe (cm)", "num"), ("export_dpi", "DPI", "num")]
FILTERS = {"png": "PNG-Bild (*.png)", "pdf": "PDF (*.pdf)", "svg": "SVG (*.svg)", "pgf": "PGF für LaTeX (*.pgf)"}


def _clean(d: dict, defaults: dict) -> dict:
    """Nur Abweichungen vom Default speichern → Projektdatei bleibt klein, neue Defaults greifen."""
    return {k: v for k, v in d.items() if v != defaults.get(k) and (v is not None or defaults.get(k) is not None)}


class AttrCmd(QUndoCommand):
    """Attribut eines Modellobjekts setzen (Page.plot, Page.show_plot, Project.style), danach after()."""

    def __init__(self, obj, attr: str, new, text: str, after):
        super().__init__(text)
        self.obj, self.attr, self.old, self.new, self.after = obj, attr, getattr(obj, attr), new, after

    def redo(self):
        setattr(self.obj, self.attr, self.new)
        self.after()

    def undo(self):
        setattr(self.obj, self.attr, self.old)
        self.after()


class PlotPanel(QWidget):
    def __init__(self, page: Page, project: Project, stack):
        super().__init__()
        self.setObjectName("page")
        self.page, self.project, self.stack = page, project, stack
        self.canvas = FigureCanvasQTAgg(Figure(layout="constrained"))
        self.canvas.mpl_connect("button_press_event", lambda e: e.dblclick and self.edit_axes())
        self.timer = QTimer(self, singleShot=True, interval=0)  # bündelt dataChanged + headerDataChanged
        self.timer.timeout.connect(self.redraw)
        bar = QHBoxLayout()
        for text, tip, slot in [("⇄ x↔y", "Achsen tauschen", self.swap),
                                ("Achsen …", "Titel, Beschriftung, Bereiche, Log (Doppelklick in den Plot)",
                                 self.edit_axes),
                                ("Export …", "PNG/PDF/SVG/PGF mit Größe und DPI", self.export)]:
            b = QToolButton(text=text, toolTip=tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.canvas, 1)
        self.redraw()

    def schedule(self, *_):
        self.timer.start()

    def redraw(self):
        fig = self.canvas.figure
        try:
            plot.draw(fig, self.page, self.project.style)
        except (ValueError, TypeError) as e:  # z.B. unpassende Achsengrenzen
            fig.clear()
            fig.text(0.5, 0.5, f"Plot nicht darstellbar:\n{e}", ha="center", va="center", wrap=True)
        self.canvas.draw_idle()

    def set_plot(self, new: dict, text: str):
        new = _clean(new, plot.PLOT)
        if new != self.page.plot:
            self.stack.push(AttrCmd(self.page, "plot", new, text, self.redraw))

    def swap(self):
        self.set_plot({**self.page.plot, "swap": not self.page.plot.get("swap", False)}, "Achsen tauschen")

    def edit_axes(self):
        v = ask("Achsen & Beschriftung", AXES_SPEC, {**plot.PLOT, **self.page.plot}, self)
        if v is not None:
            self.set_plot(v, "Achsen ändern")

    def export(self):
        st = {**plot.STYLE, **self.project.style}
        v = ask("Export", EXPORT_SPEC, st, self)
        if v is None:
            return
        if v["export_dpi"]:
            v["export_dpi"] = round(v["export_dpi"])
        if not all(x and x > 0 for x in v.values()):  # fängt auch None/NaN
            QMessageBox.warning(self, "Export", "Breite, Höhe und DPI müssen größer als 0 sein.")
            return
        if max(v["export_w"], v["export_h"]) * plot.CM * v["export_dpi"] > 20000:
            QMessageBox.warning(self, "Export", "Bild zu groß (max. 20000 Pixel pro Seite).")
            return
        f, flt = QFileDialog.getSaveFileName(self, "Plot exportieren", self.page.title, ";;".join(FILTERS.values()))
        if not f:
            return
        ext = next(k for k, t in FILTERS.items() if t == flt) if flt in FILTERS.values() else "png"
        if not f.lower().endswith(tuple("." + e for e in plot.EXPORT_FORMATS)):
            f += "." + ext
        try:
            plot.export(self.page, self.project.style, f, v["export_w"], v["export_h"], v["export_dpi"])
        except (OSError, RuntimeError, ValueError, MemoryError) as e:  # PGF ohne LaTeX → RuntimeError
            QMessageBox.critical(self, "Export fehlgeschlagen", str(e))
            return
        new = _clean({**self.project.style, **v}, plot.STYLE)  # Größe erst nach Erfolg merken
        if new != self.project.style:
            self.stack.push(AttrCmd(self.project, "style", new, "Exportgröße", lambda: None))


def edit_style(project: Project, stack, parent, after) -> None:
    v = ask("Plot-Stil (Projekt)", STYLE_SPEC, {**plot.STYLE, **project.style}, parent)
    if v is None:
        return
    for k in ("markersize", "linewidth", "capsize", "fontsize"):
        if v[k] is None or not v[k] >= 0 or (k == "fontsize" and v[k] == 0):  # auch NaN
            v[k] = plot.STYLE[k]
    new = _clean({**project.style, **v}, plot.STYLE)
    if new != project.style:
        stack.push(AttrCmd(project, "style", new, "Plot-Stil", after))


def series_style(style: dict, parent) -> dict | None:
    v = ask("Reihen-Stil (leer = Projektstil)", SERIES_SPEC, {**plot.SERIES, **style}, parent)
    return None if v is None else _clean(v, plot.SERIES)
