"""Hauptfenster: Seiten-Tabs, je Seite Splitter Tabellen | Plot, Menüs, ein Undo-Stack pro Projekt."""
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QActionGroup, QKeySequence, QUndoStack
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QInputDialog, QMainWindow,
                               QMessageBox, QSplitter, QTabWidget, QToolButton, QWidget)

from .model import Page, Project, Table
from .tables import AddTableCmd, TableTile, TableView, paste_decimal, settings

FILTER = "Kurvenwerk-Projekt (*.kwproj);;JSON (*.json)"


class PageView(QSplitter):
    def __init__(self, page: Page, stack: QUndoStack):
        super().__init__(Qt.Horizontal)
        self.setObjectName("page")
        self.page, self.stack = page, stack
        tables = QWidget()
        tables.setObjectName("page")
        self.row = QHBoxLayout(tables)
        add = QToolButton(text="+", toolTip="Tabelle hinzufügen")
        add.clicked.connect(self.add_table)
        self.row.addWidget(add, 0, Qt.AlignTop)
        self.tiles: list[TableTile] = []
        for t in page.tables:
            self.insert_tile(TableTile(t, stack))
        self.addWidget(tables)
        self.canvas = FigureCanvasQTAgg(Figure(layout="constrained"))
        self.canvas.figure.add_subplot()
        self.addWidget(self.canvas)
        self.canvas.setVisible(page.show_plot)
        self.setSizes([1, 1])

    def insert_tile(self, tile: TableTile):
        self.row.insertWidget(len(self.tiles), tile, 1)
        self.tiles.append(tile)
        tile.view.tile.connect(lambda d, r, c, t=tile: self.jump(t, d, r, c))
        tile.show()

    def remove_tile(self, tile: TableTile):
        self.tiles.remove(tile)
        tile.view.tile.disconnect()
        self.row.removeWidget(tile)
        tile.setParent(None)  # Objekt lebt im AddTableCmd weiter

    def add_table(self):
        self.stack.push(AddTableCmd(self, Table(f"Tabelle {len(self.page.tables) + 1}")))
        self.tiles[-1].view.setFocus()

    def jump(self, tile: TableTile, d: int, r: int, c: int):
        i = self.tiles.index(tile) + d
        if not 0 <= i < len(self.tiles):
            return  # am Rand bleiben
        v = self.tiles[i].view
        m = v.model()
        c = m.columnCount() - 1 if c < 0 else min(c, m.columnCount() - 1)
        v.setCurrentIndex(m.index(min(r, m.rowCount() - 1), c))
        v.setFocus()


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
        self.stack = QUndoStack(self)
        self.stack.indexChanged.connect(self._changed)

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
        e = self.menuBar().addMenu("&Bearbeiten")
        e.addAction(self.stack.createUndoAction(self, "&Rückgängig"))
        e.actions()[-1].setShortcut(QKeySequence.Undo)
        e.addAction(self.stack.createRedoAction(self, "&Wiederholen"))
        e.actions()[-1].setShortcut(QKeySequence.Redo)
        e.addSeparator()
        dm = e.addMenu("&Dezimaltrenner beim Einfügen")
        group = QActionGroup(self)
        for text, val in [("&Automatisch", "auto"), ("&Punkt  1.5", "."), ("&Komma  1,5", ",")]:
            a = dm.addAction(text, lambda v=val: settings().setValue("paste/decimal", v))
            a.setCheckable(True)
            a.setChecked(val == paste_decimal())
            group.addAction(a)
        t = self.menuBar().addMenu("&Tabelle")
        t.addAction("&Neue Tabelle", QKeySequence("Ctrl+Shift+T"), lambda: self.page_view().add_table())
        t.addAction("&Y-Spalte hinzufügen", QKeySequence("Ctrl+Shift+Y"),
                    lambda: (v := self.table_view()) and v.model().add_y())
        t.addAction("Spalte &bearbeiten …", QKeySequence("Ctrl+Shift+E"),
                    lambda: (v := self.table_view()) and v.edit_column(v.currentIndex().column()))
        t.addAction("Spalten&werte setzen …", QKeySequence("Ctrl+Shift+F"),
                    lambda: (v := self.table_view()) and v.set_values(v.currentIndex().column()))
        s = self.menuBar().addMenu("&Seite")
        s.addAction("&Hinzufügen", QKeySequence("Ctrl+T"), self.add_page)
        s.addAction("&Umbenennen …", QKeySequence("F2"), lambda: self.rename_page(self.tabs.currentIndex()))
        s.addAction("&Löschen", QKeySequence("Ctrl+W"), lambda: self.delete_page(self.tabs.currentIndex()))

        self.set_project(Project(), None)

    def page_view(self) -> PageView:
        return self.tabs.currentWidget()

    def table_view(self) -> TableView | None:
        """Fokussierte Tabelle, sonst die erste der aktuellen Seite."""
        w = QApplication.focusWidget()
        if isinstance(w, TableView):
            return w
        tiles = self.page_view().tiles
        return tiles[0].view if tiles else None

    # --- Projekt ---
    def set_project(self, project: Project, path: Path | None):
        self.project, self.path = project, path
        if not project.pages:
            project.pages.append(Page())  # Datei mit 'pages: []' → UI braucht eine Seite
        self.stack.clear()
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()
        for p in project.pages:
            self.tabs.addTab(PageView(p, self.stack), p.title)
        self.dirty = False
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
        self.stack.setClean()
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
        self.tabs.setCurrentIndex(self.tabs.addTab(PageView(p, self.stack), p.title))
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
        # ponytail: Undo-Verlauf verfällt beim Seitenlöschen (Kommandos zeigen auf die Kacheln der Seite)
        self.stack.clear()
        w = self.tabs.widget(i)
        self.tabs.removeTab(i)
        w.deleteLater()
        self._changed()
