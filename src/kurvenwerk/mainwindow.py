"""Hauptfenster: Seiten-Tabs, je Seite Splitter Tabellen | Plot, Menü Datei."""
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QMainWindow, QMessageBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton,
                               QWidget)

from .model import Page, Project

FILTER = "Kurvenwerk-Projekt (*.kwproj);;JSON (*.json)"


class PageView(QSplitter):
    def __init__(self, page: Page):
        super().__init__(Qt.Horizontal)
        self.setObjectName("page")
        tables = QWidget()
        tables.setObjectName("page")
        lay = QHBoxLayout(tables)
        for t in page.tables:
            lay.addWidget(self._table(t))
        self.addWidget(tables)
        self.canvas = FigureCanvasQTAgg(Figure(layout="constrained"))
        self.canvas.figure.add_subplot()
        self.addWidget(self.canvas)
        self.canvas.setVisible(page.show_plot)
        self.setSizes([1, 1])

    @staticmethod
    def _table(t) -> QTableWidget:
        # ponytail: nur Anzeige; Bearbeiten + Rückschreiben ins Modell kommt mit Phase 1 (Tabellen-Widget)
        rows = max((len(c.values) for c in t.columns), default=0)
        w = QTableWidget(max(rows, 20), len(t.columns))
        w.setHorizontalHeaderLabels([f"{c.name} / {c.unit}\n{c.role}" if c.unit else f"{c.name}\n{c.role}"
                                     for c in t.columns])
        w.setEditTriggers(QTableWidget.NoEditTriggers)
        w.setAlternatingRowColors(True)
        for j, c in enumerate(t.columns):
            for i, v in enumerate(c.values):
                if v is not None:
                    w.setItem(i, j, QTableWidgetItem(repr(v)))
        return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1200, 750)
        self.tabs = QTabWidget(documentMode=True, tabsClosable=True)
        self.tabs.tabCloseRequested.connect(self.delete_page)
        self.tabs.tabBarDoubleClicked.connect(self.rename_page)
        add = QToolButton(text="+", toolTip="Seite hinzufügen")
        add.clicked.connect(self.add_page)
        self.tabs.setCornerWidget(add, Qt.TopRightCorner)
        self.setCentralWidget(self.tabs)

        m = self.menuBar().addMenu("&Datei")
        for text, key, slot in [("&Neu", QKeySequence.New, self.new),
                                ("Ö&ffnen …", QKeySequence.Open, self.open),
                                ("&Speichern", QKeySequence.Save, self.save),
                                ("Speichern &unter …", QKeySequence.SaveAs, self.save_as),
                                (None, None, None),
                                ("&Beenden", QKeySequence.Quit, self.close)]:
            if text is None:
                m.addSeparator()
            else:
                m.addAction(text, key, slot)
        s = self.menuBar().addMenu("&Seite")
        s.addAction("&Hinzufügen", QKeySequence("Ctrl+T"), self.add_page)
        s.addAction("&Umbenennen …", QKeySequence("F2"), lambda: self.rename_page(self.tabs.currentIndex()))
        s.addAction("&Löschen", QKeySequence("Ctrl+W"), lambda: self.delete_page(self.tabs.currentIndex()))

        self.set_project(Project(), None)

    # --- Projekt ---
    def set_project(self, project: Project, path: Path | None):
        self.project, self.path, self.dirty = project, path, False
        self.tabs.clear()
        for p in project.pages:
            self.tabs.addTab(PageView(p), p.title)
        self._update_title()

    def _changed(self):
        self.dirty = True
        self._update_title()

    def _update_title(self):
        name = self.path.name if self.path else "Unbenannt"
        self.setWindowTitle(f"{name}{' *' if self.dirty else ''} — Kurvenwerk")

    def _may_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Ungespeicherte Änderungen", "Änderungen speichern?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        return r == QMessageBox.Discard or (r == QMessageBox.Save and self.save())

    def new(self):
        if self._may_discard():
            self.set_project(Project(), None)

    def open(self):
        if not self._may_discard():
            return
        f, _ = QFileDialog.getOpenFileName(self, "Projekt öffnen", "", FILTER)
        if not f:
            return
        try:
            self.set_project(Project.load(f), Path(f))
        except (OSError, ValueError, KeyError, TypeError) as e:
            QMessageBox.critical(self, "Öffnen fehlgeschlagen", f"{Path(f).name}:\n{e}")

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        try:
            self.project.save(self.path)
        except OSError as e:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(e))
            return False
        self.dirty = False
        self._update_title()
        return True

    def save_as(self) -> bool:
        f, _ = QFileDialog.getSaveFileName(self, "Projekt speichern", "", FILTER)
        if not f:
            return False
        self.path = Path(f)
        return self.save()

    def closeEvent(self, e):
        e.accept() if self._may_discard() else e.ignore()

    # --- Seiten ---
    def add_page(self):
        p = Page(f"Seite {len(self.project.pages) + 1}")
        self.project.pages.append(p)
        self.tabs.setCurrentIndex(self.tabs.addTab(PageView(p), p.title))
        self._changed()

    def rename_page(self, i: int):
        if i < 0:
            return
        p = self.project.pages[i]
        title, ok = QInputDialog.getText(self, "Seite umbenennen", "Titel:", text=p.title)
        if ok and title.strip() and title.strip() != p.title:
            p.title = title.strip()
            self.tabs.setTabText(i, p.title)
            self._changed()

    def delete_page(self, i: int):
        if i < 0 or len(self.project.pages) == 1:
            return  # mindestens eine Seite bleibt
        p = self.project.pages[i]
        if QMessageBox.question(self, "Seite löschen", f"Seite „{p.title}“ löschen?") != QMessageBox.Yes:
            return
        del self.project.pages[i]
        w = self.tabs.widget(i)
        self.tabs.removeTab(i)
        w.deleteLater()
        self._changed()
