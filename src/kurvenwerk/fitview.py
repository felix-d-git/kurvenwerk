"""Fit-Dialog einer Y-Spalte: Vorlage/Formel, Parameter (Start, Grenzen, fix), Bereich, Band, Vorschau."""
import json
from dataclasses import replace

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem)

from . import fit as fitting
from . import plot
from .formula import FormulaError, number

OWN = "fit/templates"  # eigene Vorlagen gerätweit in QSettings, nicht im Projekt
COLS = ("Startwert", "min", "max")


def own_templates() -> dict:
    try:
        return json.loads(QSettings("Kurvenwerk", "Kurvenwerk").value(OWN, "{}"))
    except (TypeError, ValueError):
        return {}


def _num(t: str):
    return number(t) if t.strip() else None


def _fmt(v) -> str:
    return "" if v is None else f"{v:.10g}"


class FitDialog(QDialog):
    """result_fit: neues Column.fit ({} = Fit entfernen) nach accept()."""

    def __init__(self, s: plot.Series, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Fit {s.ycol.name}")
        self.s, self.f = s, {**fitting.FIT, **s.ycol.fit}
        self.result_fit = None
        lay = QFormLayout(self)

        self.tpl = QComboBox()
        self.templates = {**fitting.TEMPLATES, **{f"Polynom Grad {n}": fitting.polynomial(n) for n in range(2, 7)},
                          **own_templates()}
        self.tpl.addItems(["– Vorlage wählen –", *self.templates])
        self.tpl.activated.connect(lambda i: i and self.formula.setText(self.templates[self.tpl.itemText(i)]))
        save = QPushButton("Als Vorlage speichern …")
        save.clicked.connect(self.save_template)
        row = QHBoxLayout()
        row.addWidget(self.tpl, 1)
        row.addWidget(save)
        lay.addRow("Vorlage", row)

        self.formula = QLineEdit(self.f["formula"], placeholderText="y(x), z.B. a*exp(-x/tau) + c")
        self.formula.textChanged.connect(self.rebuild)
        lay.addRow("Formel y =", self.formula)
        self.params = QTableWidget(0, 4)
        self.params.setHorizontalHeaderLabels([*COLS, "fix"])
        lay.addRow("Parameter", self.params)

        self.xmin, self.xmax = (QLineEdit(_fmt(self.f[k]), placeholderText="alle") for k in ("xmin", "xmax"))
        row = QHBoxLayout()
        row.addWidget(self.xmin)
        row.addWidget(QLabel("bis"))
        row.addWidget(self.xmax)
        lay.addRow("Fit-Bereich x", row)

        self.band = QComboBox()
        for k, v in fitting.BANDS.items():
            self.band.addItem(v, k)
        self.band.setCurrentIndex(max(0, self.band.findData(self.f["band"])))
        self.level = QDoubleSpinBox(decimals=3, minimum=0.5, maximum=0.999, singleStep=0.01, value=self.f["level"])
        row = QHBoxLayout()
        row.addWidget(self.band, 1)
        row.addWidget(QLabel("Niveau"))
        row.addWidget(self.level)
        lay.addRow("Band", row)

        self.excluded = list(self.f["excluded"])
        self.exl = QLabel()
        reset = QPushButton("alle wieder einschließen")
        reset.clicked.connect(lambda: (self.excluded.clear(), self.show_excluded()))
        row = QHBoxLayout()
        row.addWidget(self.exl, 1)
        row.addWidget(reset)
        lay.addRow("Ausschluss", row)
        self.show_excluded()

        self.msg = QLabel(wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        lay.addRow(self.msg)
        row = QHBoxLayout()
        for text, slot in [("Fitten", self.preview), ("Ergebnis → Startwerte", self.adopt),
                           ("Fit entfernen", self.remove), ("OK", self.ok), ("Abbrechen", self.reject)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addRow(row)
        self.result = None
        self.rebuild()

    def show_excluded(self):
        self.exl.setText(f"{len(self.excluded)} Punkte ausgeschlossen (Klick auf Punkt im Plot schaltet um)")

    def rebuild(self):
        """Parametertabelle aus der Formel; bekannte Werte bleiben erhalten."""
        self.result = None
        try:
            names = fitting.model(self.formula.text())[1] if self.formula.text().strip() else []
        except ValueError as e:  # FormulaError, FitError (keine Parameter)
            self.msg.setText(str(e))
            return
        self.msg.setText("")
        old = {**self.f["params"], **self.read_params(strict=False)}
        self.params.setRowCount(len(names))
        self.params.setVerticalHeaderLabels(names)
        for i, n in enumerate(names):
            p = old.get(n, {})
            for j, k in enumerate(("value", "min", "max")):
                self.params.setItem(i, j, QTableWidgetItem(_fmt(p.get(k))))
            fix = QTableWidgetItem()
            fix.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            fix.setCheckState(Qt.Checked if p.get("fixed") else Qt.Unchecked)
            self.params.setItem(i, 3, fix)

    def read_params(self, strict=True) -> dict:
        out = {}
        for i in range(self.params.rowCount()):
            n = self.params.verticalHeaderItem(i).text()
            p = {}
            for j, k in enumerate(("value", "min", "max")):
                try:
                    p[k] = _num(self.params.item(i, j).text())
                except FormulaError:
                    if strict:
                        raise FormulaError(f"{n}, {COLS[j]}: keine Zahl") from None
            p["fixed"] = self.params.item(i, 3).checkState() == Qt.Checked
            out[n] = {k: v for k, v in p.items() if v is not None and v is not False}
        return out

    def values(self) -> dict:
        """Formularinhalt → Column.fit, wirft FormulaError bei ungültigen Zahlen."""
        try:
            xr = [_num(w.text()) for w in (self.xmin, self.xmax)]
        except FormulaError as e:
            raise FormulaError(f"Fit-Bereich: {e}") from None
        new = {"formula": self.formula.text().strip(), "params": self.read_params(), "xmin": xr[0], "xmax": xr[1],
               "excluded": sorted(self.excluded), "band": self.band.currentData(), "level": self.level.value()}
        return {k: v for k, v in new.items() if v != fitting.FIT[k]}

    def preview(self):
        try:
            new = self.values()
            self.result = plot.run_fit(replace(self.s, ycol=replace(self.s.ycol, fit=new)))[0]
        except ValueError as e:  # FitError, FormulaError
            self.result = None
            self.msg.setText(f"<span style='color:#d62728'>{e}</span>")
            return
        r = self.result
        lines = [f"{n} = {v:.6g} ± {e:.2g}" + ("" if fr else " (fix)")
                 for n, v, e, fr in zip(r.params, r.values, r.errors, r.free)]
        chi = f"χ²/ndf = {r.chi2:.4g}/{r.ndf}" if r.absolute else f"Residuen² = {r.chi2:.4g}, ndf = {r.ndf}"
        self.msg.setText("<br>".join(lines + [chi, f"Methode: {r.method}"]))

    def adopt(self):
        if self.result is None:
            self.preview()
        if self.result is not None:
            for i, v in enumerate(self.result.values):
                self.params.item(i, 0).setText(_fmt(float(v)))

    def save_template(self):
        t = self.formula.text().strip()
        if not t:
            return
        name, ok = QInputDialog.getText(self, "Vorlage speichern", "Name der Vorlage:")
        if ok and name.strip():
            own = {**own_templates(), name.strip(): t}
            QSettings("Kurvenwerk", "Kurvenwerk").setValue(OWN, json.dumps(own))
            self.templates[name.strip()] = t
            if self.tpl.findText(name.strip()) < 0:
                self.tpl.addItem(name.strip())

    def remove(self):
        self.result_fit = {}
        self.accept()

    def ok(self):
        try:
            new = self.values()
            if new.get("formula"):
                fitting.model(new["formula"])
        except ValueError as e:
            self.msg.setText(f"<span style='color:#d62728'>{e}</span>")
            return
        self.result_fit = new if new.get("formula") else {}
        self.accept()
