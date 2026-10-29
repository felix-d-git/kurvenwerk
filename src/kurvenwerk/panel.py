"""Rechtes Panel einer Seite: Beschriftung, Achsen und Schalter direkt sichtbar; Fits je Reihe mit Kurzergebnis."""
import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from . import fit as fitting
from . import plot
from .fitview import FitDialog, save_template
from .plotview import AttrCmd, _clean, convert
from .stats import fit_short
from .tables import result_opts

LINEAR = fitting.TEMPLATES["Linear"]
LABELS = [("title", "Titel"), ("xlabel", "x-Achse"), ("ylabel", "y-Achse"), ("y2label", "2. y-Achse")]
AXES = [("x", "x"), ("y", "y"), ("y2", "2. y")]
TOGGLES = [("legend", "Legende"), ("grid", "Gitter"), ("page_title", "Seitentitel"), ("swap", "Achsen x↔y"),
           ("residuals", "Residuenplot")]
RED = "<span style='color:#d62728'>{}</span>"


def _fmt(v) -> str:
    return "" if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def is_linear(formula: str) -> bool:
    return formula.replace(" ", "") == LINEAR.replace(" ", "")


def section(text: str) -> QLabel:
    return QLabel(text, objectName="section")


class FitRow(QWidget):
    """Eine Y-Reihe: Häkchen Gerade / 2. y-Achse, Knopf Fit-Dialog, eigene Formel, Kurzergebnis."""

    def __init__(self, panel: "SettingsPanel"):
        super().__init__()
        self.panel, self.s = panel, None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        top = QHBoxLayout()
        self.name = QLabel(textFormat=Qt.PlainText)
        self.line = QCheckBox("Gerade", toolTip="Fit y = a*x + b")
        self.line.toggled.connect(self.set_line)
        self.y2 = QCheckBox("2. y", toolTip="Reihe auf der zweiten y-Achse")
        self.y2.toggled.connect(self.set_y2)
        more = QToolButton(text="Fit …", toolTip="Fit-Typ, Startwerte, Bereich, Band (Fit-Dialog)")
        more.clicked.connect(self.dialog)
        top.addWidget(self.name, 1)
        for w in (self.line, self.y2, more):
            top.addWidget(w)
        lay.addLayout(top)
        row = QHBoxLayout()
        self.formula = QLineEdit(placeholderText="eigene Funktion, z.B. a*x^2 + b")
        self.formula.textChanged.connect(self.detect)
        self.formula.editingFinished.connect(self.commit)
        star = QToolButton(text="☆", toolTip="Funktion als Vorlage speichern")
        star.clicked.connect(self.save)
        row.addWidget(self.formula, 1)
        row.addWidget(star)
        lay.addLayout(row)
        self.result = QLabel(objectName="result", wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        lay.addWidget(self.result)

    def update(self, s: plot.Series, title: str):
        self.s = s
        f = s.ycol.fit.get("formula", "")
        self.name.setText(title)
        for w, on in ((self.line, is_linear(f)), (self.y2, s.ycol.style.get("axis") == "y2")):
            w.blockSignals(True)
            w.setChecked(on)
            w.blockSignals(False)
        if not self.formula.hasFocus():
            self.formula.blockSignals(True)
            self.formula.setText(f)
            self.formula.blockSignals(False)
        if not f:
            self.result.setText("kein Fit")
            return
        try:
            # ponytail: Fit läuft für Plot und Panel je einmal; Ergebnis aus plot.draw teilen, falls es zu langsam wird
            r = plot.run_fit(s)[0]
        except ValueError as e:  # FitError, FormulaError
            self.result.setText(RED.format(html.escape(str(e))))
            return
        self.result.setText(f"<pre>{html.escape(fit_short(r, **result_opts()))}</pre>")

    def set_fit(self, new: dict):
        new = _clean(new, fitting.FIT)
        if new != self.s.ycol.fit:
            self.panel.set_fit(self.s.ycol, new)

    def set_line(self, on: bool):
        if on:
            self.set_fit({**self.s.ycol.fit, "formula": LINEAR})
        else:
            self.set_fit({})

    def set_y2(self, on: bool):
        new = _clean({**self.s.ycol.style, "axis": "y2" if on else "y"}, plot.SERIES)
        self.panel.set_style(self.s.ycol, new)

    def detect(self, text: str):
        """Beim Tippen: erkannte Parameter bzw. Fehler zeigen; gefittet wird erst mit Enter."""
        if not text.strip():
            self.result.setText("Enter ohne Funktion entfernt den Fit")
            return
        try:
            names = fitting.model(text)[1]
        except ValueError as e:
            self.result.setText(RED.format(html.escape(str(e))))
            return
        self.result.setText(html.escape(f"Parameter: {', '.join(names)} — Enter fittet"))

    def commit(self):
        t = self.formula.text().strip()
        if self.s is None or t == self.s.ycol.fit.get("formula", ""):
            return
        if t:
            try:
                fitting.model(t)
            except ValueError:
                return  # Fehler steht schon unter dem Feld
            self.set_fit({**self.s.ycol.fit, "formula": t})
        else:
            self.set_fit({})

    def save(self):
        t = self.formula.text().strip()
        try:
            fitting.model(t)
        except ValueError as e:
            self.result.setText(RED.format(html.escape(str(e))))
            return
        name, ok = QInputDialog.getText(self, "Vorlage speichern", f"Name der Vorlage für {t}:")
        if ok and name.strip():
            save_template(name.strip(), t)
            self.result.setText(html.escape(f"Vorlage „{name.strip()}“ gespeichert (Fit-Dialog → Vorlage)"))

    def dialog(self):
        d = FitDialog(self.s, self)
        if d.exec() and d.result_fit is not None:
            self.set_fit(d.result_fit)


class SettingsPanel(QScrollArea):
    """Liest Page.plot/Project.style, schreibt über den Undo-Stack; aktualisiert sich nach jedem Neuzeichnen."""

    def __init__(self, page, project, stack, plotview, set_fit, set_style):
        super().__init__(widgetResizable=True, frameShape=QFrame.NoFrame)
        self.page, self.project, self.stack, self.plotview = page, project, stack, plotview
        self.set_fit, self.set_style = set_fit, set_style
        self.after_style = plotview.redraw  # MainWindow ersetzt durch „alle Seiten neu zeichnen“
        box = QFrame(objectName="panel")
        lay = QVBoxLayout(box)
        lay.addWidget(QLabel("Einstellungen", objectName="panelTitle"))
        self.edits = {}  # Schlüssel → (QLineEdit, Art für convert)

        def edit(key, kind, placeholder):
            w = QLineEdit(placeholderText=placeholder)
            w.editingFinished.connect(lambda: self.commit(key))
            self.edits[key] = (w, kind)
            return w

        lay.addWidget(section("Beschriftung"))
        g = QGridLayout()
        for i, (key, text) in enumerate(LABELS):
            g.addWidget(QLabel(text), i, 0)
            g.addWidget(edit(key, "math", "auto · Mathe in $…$"), i, 1)
        lay.addLayout(g)

        lay.addWidget(section("Achsen"))
        g = QGridLayout()
        for j, h in enumerate(("min", "max", "log"), 1):
            g.addWidget(QLabel(h, objectName="hint"), 0, j)
        self.checks = {}
        for i, (a, text) in enumerate(AXES, 1):
            g.addWidget(QLabel(text), i, 0)
            g.addWidget(edit(f"{a}min", "num", "auto"), i, 1)
            g.addWidget(edit(f"{a}max", "num", "auto"), i, 2)
            g.addWidget(self.check(f"{a}log", ""), i, 3)
        lay.addLayout(g)
        g = QGridLayout()
        for i, (key, text) in enumerate(TOGGLES):
            g.addWidget(self.check(key, text), i // 2, i % 2)
        lay.addLayout(g)
        self.msg = QLabel(wordWrap=True)
        lay.addWidget(self.msg)

        lay.addWidget(section("Fits"))
        self.fits = QVBoxLayout()
        lay.addLayout(self.fits)
        self.none = QLabel("Keine Reihe mit Daten (X und Y)", objectName="hint")
        lay.addWidget(self.none)
        lay.addStretch()
        self.setWidget(box)
        self.rows, self.keys = [], None
        plotview.redrawn.connect(self.refresh)
        self.refresh()

    def check(self, key: str, text: str) -> QCheckBox:
        w = QCheckBox(text)
        w.toggled.connect(lambda on: self.toggle(key, on))
        self.checks[key] = w
        return w

    def values(self) -> dict:
        return {**plot.PLOT, **self.page.plot, "grid": {**plot.STYLE, **self.project.style}["grid"]}

    def commit(self, key: str):
        w, kind = self.edits[key]
        try:
            v = convert(kind, w.text().strip())
        except ValueError as e:
            self.msg.setText(RED.format(html.escape(f"{key}: {e}")))
            return
        self.msg.clear()
        self.plotview.set_plot({**self.page.plot, key: v}, "Achsen ändern")

    def toggle(self, key: str, on: bool):
        if key == "grid":  # Gitter ist Projektstil → gilt für alle Seiten
            new = _clean({**self.project.style, "grid": on}, plot.STYLE)
            self.stack.push(AttrCmd(self.project, "style", new, "Gitter", self.after_style))
        else:
            self.plotview.set_plot({**self.page.plot, key: on}, "Achsen ändern")

    def refresh(self):
        v = self.values()
        for key, (w, _) in self.edits.items():
            if not w.hasFocus():
                w.setText(_fmt(v[key]))
        for key, w in self.checks.items():
            w.blockSignals(True)
            w.setChecked(bool(v[key]))
            w.blockSignals(False)
        many = len(self.page.tables) > 1
        found = [(s, plot.heading(s.ycol) + (f" ({t.name})" if many and t.name else ""))
                 for t in self.page.tables for s in plot.series(t)]
        # Spaltenobjekte wechseln bei jedem Undo-Schritt → Zeilen über Position wiedererkennen
        keys = [(ti, j) for ti, t in enumerate(self.page.tables) for j, c in enumerate(t.columns)
                if any(s.ycol is c for s, _ in found)]
        if keys != self.keys:
            self.keys = keys
            for r in self.rows:
                r.deleteLater()
            self.rows = [FitRow(self) for _ in found]
            for r in self.rows:
                self.fits.addWidget(r)
        for r, (s, title) in zip(self.rows, found):
            r.update(s, title)
        self.none.setVisible(not found)
