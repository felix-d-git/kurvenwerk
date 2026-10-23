"""Auswertungsleiste unter einer Seite: Statistik (Auswahl oder Spalte), t-Test, Welch-Vergleich, Histogramm."""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QToolButton, QVBoxLayout)

from . import plot
from .model import Page
from .stats import (describe, outliers_grubbs, outliers_iqr, summary, ttest, ttest_text, welch, welch_text)
from .tables import result_opts

OUT = "#d62728"


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ".")) if text.strip() else None
    except ValueError:
        return None


def _label(text: str) -> QLabel:
    return QLabel(text, textFormat=Qt.PlainText, wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)


def columns(page: Page) -> list[tuple[str, np.ndarray, np.ndarray | None, str, object]]:
    """Alle Spalten der Seite: (Beschriftung, Werte, u-Werte für den gewichteten Mittelwert, Einheit, Spalte)."""
    out = []
    for t in page.tables:
        cols = t.columns
        for j, c in enumerate(cols):
            x = np.array([np.nan if v is None else v for v in c.values], float)
            e = plot._error(cols, j) if c.role in ("X", "Y") else None
            dx = None
            if e is not None:
                dx = np.full(len(x), np.nan)
                ev = np.abs(np.array([np.nan if v is None else v for v in e.values[:len(x)]], float))
                dx[:len(ev)] = ev
            name = c.name or c.role
            out.append((f"{t.name}: {name}" + (f" / {c.unit}" if c.unit else ""), x, dx, c.unit, c))
    return out


class EvalBar(QFrame):
    def __init__(self, page: Page):
        super().__init__(objectName="panel")
        self.page, self.selection, self.cols = page, ({"n": 0}, ""), []
        self.timer = QTimer(self, singleShot=True, interval=0)
        self.timer.timeout.connect(self.refresh)
        self.a, self.b = QComboBox(), QComboBox()
        self.mu0, self.alpha = QLineEdit(placeholderText="Sollwert μ₀"), QLineEdit("0.05")
        self.method = QComboBox()
        self.method.addItems(["IQR (1.5)", "Grubbs (α)"])
        for w in (self.a, self.b, self.method):
            w.currentIndexChanged.connect(self.schedule)
        for w in (self.mu0, self.alpha):
            w.textChanged.connect(self.schedule)
        self.desc, self.ttest, self.welch, self.out = (_label("") for _ in range(4))
        self.desc_title = QLabel(objectName="section", textFormat=Qt.PlainText)
        copy = QToolButton(text="Kopieren ▾", toolTip="Ergebnisse als Text oder siunitx",
                           popupMode=QToolButton.InstantPopup)
        copy.setMenu(self.copy_menu())
        self.canvas = FigureCanvasQTAgg(Figure(figsize=(3, 1.4), layout="constrained"))
        self.canvas.setMinimumSize(220, 110)

        head = QHBoxLayout()
        head.addWidget(QLabel("Auswertung", objectName="panelTitle"))
        head.addWidget(QLabel("Spalte"))
        head.addWidget(self.a, 1)
        head.addStretch()
        head.addWidget(copy)
        tiles = QHBoxLayout()
        t1 = QVBoxLayout()
        t1.addWidget(self.desc_title)
        t1.addWidget(self.desc)
        t1.addStretch()
        t2 = QGridLayout()
        t2.addWidget(QLabel("t-Test gegen Sollwert", objectName="section"), 0, 0, 1, 2)
        t2.addWidget(self.mu0, 1, 0)
        t2.addWidget(QLabel("α"), 1, 1, Qt.AlignRight)
        t2.addWidget(self.alpha, 1, 2)
        t2.addWidget(self.ttest, 2, 0, 1, 3)
        t2.setRowStretch(3, 1)
        t3 = QVBoxLayout()
        t3.addWidget(QLabel("Vergleich mit (Welch-t-Test)", objectName="section"))
        t3.addWidget(self.b)
        t3.addWidget(self.welch)
        t3.addStretch()
        t4 = QGridLayout()
        t4.addWidget(QLabel("Histogramm · Ausreißer", objectName="section"), 0, 0)
        t4.addWidget(self.method, 0, 1)
        t4.addWidget(self.canvas, 1, 0, 1, 2)
        t4.addWidget(self.out, 2, 0, 1, 2)
        for t, s in [(t1, 3), (t2, 2), (t3, 2), (t4, 3)]:
            tiles.addLayout(t, s)
        lay = QVBoxLayout(self)
        lay.addLayout(head)
        lay.addLayout(tiles, 1)
        self.refresh()

    def schedule(self, *_):
        self.timer.start()

    def set_selection(self, d: dict, unit: str):
        self.selection = (d, unit)
        self.schedule()

    def _fill(self, box: QComboBox, keep, none: str | None = None):
        box.blockSignals(True)
        box.clear()
        if none:
            box.addItem(none)
        for label, *_ in self.cols:
            box.addItem(label)
        ids = [c[-1] for c in self.cols]
        i = next((i for i, c in enumerate(ids) if c is keep), None)
        box.setCurrentIndex((i + bool(none)) if i is not None else (0 if none else min(1, len(ids) - 1)))
        box.blockSignals(False)

    def _current(self, box: QComboBox, offset=0):
        i = box.currentIndex() - offset
        return self.cols[i] if 0 <= i < len(self.cols) else None

    def refresh(self):
        """Spaltenlisten neu (Tabellen/Spalten können sich geändert haben) und alles neu rechnen."""
        a, b = self._current(self.a), self._current(self.b, 1)
        self.cols = columns(self.page)
        self._fill(self.a, a and a[-1])
        self._fill(self.b, b and b[-1], "–")
        self.texts = {tex: self.report(tex) for tex in (False, True)}
        self.draw()

    def report(self, tex: bool) -> str:
        """Alle Ergebnisse als Text bzw. siunitx; setzt nebenbei (tex=False) die Kachel-Texte."""
        o = result_opts()
        a, b = self._current(self.a), self._current(self.b, 1)
        parts = []
        sel, unit = self.selection
        if sel.get("n"):
            title, d = "Auswahl", sel
        elif a:
            title, d, unit = a[0], describe(a[1], a[2]), a[3]
        else:
            title, d = "–", {"n": 0}
        s = summary(d, unit=unit, tex=tex, **o)
        if not tex:
            self.desc_title.setText(title)
            self.desc.setText(s.replace("  ·  ", "\n") if s else "keine Werte")
        if s:
            parts += [f"{title}:", s]
        mu0, alpha = _num(self.mu0.text()), _num(self.alpha.text())
        t = ""
        if a and mu0 is not None and alpha is not None and 0 < alpha < 1:
            t = ttest_text(ttest(a[1], mu0), mu0, alpha, tex)
            if t:
                parts += [f"t-Test {a[0]} gegen μ₀ = {mu0:g}:", t]
        if not tex:
            self.ttest.setText(t or ("α zwischen 0 und 1" if alpha is None or not 0 < alpha < 1
                                     else "Sollwert eingeben" if mu0 is None else "mind. 2 verschiedene Werte"))
        w = ""
        if a and b:
            w = welch_text(welch(a[1], b[1]), tex=tex, unit=a[3] if a[3] == b[3] else "", **o)
            if w:
                parts += [f"{a[0]} − {b[0]} (Welch):", w]
        if not tex:
            self.welch.setText(w or ("Zweite Spalte wählen" if not b else "je mind. 2 Werte"))
        if a:
            x = a[1]
            m = self.outliers(x)
            vals = ", ".join(f"{v:g}" for v in x[m])
            line = f"Ausreißer ({self.method.currentText()}): {vals or 'keine'}"
            parts.append(line)
            if not tex:
                self.out.setText(line)
        return "\n".join(parts)

    def outliers(self, x: np.ndarray) -> np.ndarray:
        alpha = _num(self.alpha.text())
        if self.method.currentIndex():
            return outliers_grubbs(x, alpha if alpha and 0 < alpha < 1 else 0.05)
        return outliers_iqr(x)

    def draw(self):
        fig = self.canvas.figure
        fig.clear()
        a = self._current(self.a)
        x = a[1][np.isfinite(a[1])] if a else np.array([])
        if len(x):
            ax = fig.add_subplot()
            m = self.outliers(x)
            ax.hist(x, bins="auto", color=plot.STYLE["colors"].split(",")[0])
            ax.plot(x[m], np.zeros(m.sum()), "v", color=OUT, ms=7, clip_on=False)
            ax.tick_params(labelsize=7)
        self.canvas.draw_idle()

    def copy(self, tex: bool):
        self.refresh()
        QApplication.clipboard().setText(self.texts[tex])

    def copy_menu(self) -> QMenu:
        m = QMenu("Ergebnisse &kopieren", self)
        for text, tex in [("als &Text", False), ("als &siunitx", True)]:
            m.addAction(text, lambda t=tex: self.copy(t))
        return m
