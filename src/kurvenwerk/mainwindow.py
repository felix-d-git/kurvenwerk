"""Hauptfenster: Seiten-Tabs, je Seite vierteiliges Splitter-Layout, Menüs, ein Undo-Stack pro Projekt."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QActionGroup, QKeySequence, QUndoStack
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QSplitter, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)

from . import export
from .model import Page, Project, Table
from .panel import SettingsPanel
from .plotview import AttrCmd, PlotPanel, edit_style
from .stats import summary
from .tables import AddTableCmd, RemoveTableCmd, TableTile, TableView, paste_decimal, result_opts, settings

FILTER = "Kurvenwerk-Projekt (*.kwproj);;JSON (*.json)"


def placeholder(title: str, text: str) -> QFrame:
    f = QFrame(objectName="panel")
    lay = QVBoxLayout(f)
    lay.addWidget(QLabel(title, objectName="panelTitle"))
    lay.addWidget(QLabel(text, wordWrap=True, objectName="hint"))
    lay.addStretch()
    return f


class PageView(QSplitter):
    """Vierteilig: oben Tabellen | Plot | Einstellungen, unten Auswertung; alle Bereiche zuklappbar."""
    changed = Signal()  # Beschreibung geändert (nicht im Undo-Stack)

    def __init__(self, page: Page, project: Project, stack: QUndoStack):
        super().__init__(Qt.Vertical)
        self.setObjectName("page")
        self.page, self.stack = page, stack
        tables = QWidget()
        tables.setObjectName("page")
        self.row = QHBoxLayout(tables)
        add = QToolButton(text="+", toolTip="Tabelle hinzufügen")
        add.clicked.connect(self.add_table)
        self.row.addWidget(add, 0, Qt.AlignTop)
        self.tiles: list[TableTile] = []
        self.plot = PlotPanel(page, project, stack)
        self.plot.set_fit = self.set_fit
        for t in page.tables:
            self.insert_tile(TableTile(t, stack))
        self.description = QPlainTextEdit(page.description, placeholderText="Beschreibung der Seite (Freitext)")
        self.description.textChanged.connect(self._description)
        self.left = QSplitter(Qt.Vertical)
        self.left.addWidget(tables)
        self.left.addWidget(self.description)
        self.left.setSizes([400, 100])
        self.top = QSplitter(Qt.Horizontal)
        self.top.addWidget(self.left)
        self.top.addWidget(self.plot)
        self.panel = SettingsPanel(page, project, stack, self.plot, self.set_fit, self.set_style)
        self.top.addWidget(self.panel)
        self.plot.on_dblclick = self.show_settings
        self.top.setSizes([450, 550, 220])
        self.addWidget(self.top)
        self.addWidget(placeholder("Auswertung", "Statistik, t-Tests und Histogramm folgen hier."))
        self.setSizes([600, 120])
        for s in self.splitters().values():
            s.setChildrenCollapsible(True)
            s.setHandleWidth(6)
            s.splitterMoved.connect(self.save_layout)
        self.plot.setVisible(page.show_plot)

    def splitters(self) -> dict[str, QSplitter]:
        return {"main": self, "top": self.top, "left": self.left}

    def save_layout(self):
        for k, s in self.splitters().items():
            settings().setValue(f"layout/{k}", s.saveState())

    def restore_layout(self):
        for k, s in self.splitters().items():
            if (state := settings().value(f"layout/{k}")) is not None:
                s.restoreState(state)
        self.plot.setVisible(self.page.show_plot)  # restoreState setzt auch Sichtbarkeit

    def showEvent(self, e):
        self.restore_layout()  # jede Seite übernimmt beim Anzeigen das zuletzt gezogene Layout
        super().showEvent(e)

    def _description(self):
        self.page.description = self.description.toPlainText()
        self.changed.emit()

    def _model_col(self, col):
        """(Tabellenmodell, Spaltenindex) zum Spaltenobjekt aus Plot/Panel."""
        for t in self.tiles:
            j = next((j for j, c in enumerate(t.model.table.columns) if c is col), None)
            if j is not None:
                return t.model, j
        return None, None

    def set_fit(self, col, fit: dict):
        """Fit der Spalte über das Modell ihrer Tabelle → Undo."""
        m, j = self._model_col(col)
        if m:
            m.set_fit(j, fit)

    def set_style(self, col, style: dict):
        m, j = self._model_col(col)
        if m:
            m.set_style(j, style)

    def show_settings(self):
        """Zugeklapptes Einstellungs-Panel wieder aufziehen (Doppelklick in den Plot, Strg+Umschalt+A)."""
        sizes = self.top.sizes()
        if sizes[2] < 50:
            sizes[2] = 260
            sizes[1] = max(sizes[1] - 260, 100)
            self.top.setSizes(sizes)
            self.save_layout()
        self.panel.edits["title"][0].setFocus()

    def _signals(self, tile: TableTile):
        m = tile.model
        return m.dataChanged, m.modelReset, m.headerDataChanged

    def toggle_plot(self):
        def after():
            self.plot.setVisible(self.page.show_plot)
        self.stack.push(AttrCmd(self.page, "show_plot", not self.page.show_plot, "Plot ein/aus", after))

    def insert_tile(self, tile: TableTile, i: int | None = None):
        """Kachel (und ihre Tabelle in page.tables) an Stelle i, sonst ans Ende."""
        i = len(self.tiles) if i is None else i
        self.row.insertWidget(i, tile, 1)
        self.tiles.insert(i, tile)
        if not any(t is tile.model.table for t in self.page.tables):
            self.page.tables.insert(i, tile.model.table)
        tile.view.tile.connect(lambda d, r, c, t=tile: self.jump(t, d, r, c))
        tile.remove.connect(lambda t=tile: self.remove_table(t))
        for sig in self._signals(tile):
            sig.connect(self.plot.schedule)
        tile.show()
        self.plot.schedule()

    def remove_tile(self, tile: TableTile):
        i = self.tiles.index(tile)
        del self.tiles[i], self.page.tables[i]
        tile.view.tile.disconnect()
        tile.remove.disconnect()
        for sig in self._signals(tile):
            sig.disconnect(self.plot.schedule)
        self.plot.schedule()
        self.row.removeWidget(tile)
        tile.setParent(None)  # Objekt lebt im AddTableCmd weiter

    def add_table(self):
        self.stack.push(AddTableCmd(self, Table(f"Tabelle {len(self.page.tables) + 1}")))
        self.tiles[-1].view.setFocus()

    def remove_table(self, tile: TableTile):
        self.stack.push(RemoveTableCmd(self, tile))

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
        self.stats, self.stats_label = ({"n": 0}, ""), QLabel(textFormat=Qt.PlainText,
                                                       textInteractionFlags=Qt.TextSelectableByMouse)
        self.stats_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.stats_label.customContextMenuRequested.connect(lambda p: self.copy_menu().exec(self.cursor().pos()))
        self.statusBar().addWidget(self.stats_label, 1)

        m = self.menuBar().addMenu("&Datei")
        for text, key, slot in [("&Neu", QKeySequence.New, self.new),
                                ("Ö&ffnen …", QKeySequence.Open, self.open),
                                ("&Speichern", QKeySequence.Save, self.save),
                                ("Speichern &unter …", QKeySequence.SaveAs, self.save_as),
                                (None, None, None),
                                ("Projekt e&xportieren …", QKeySequence(), self.export_project),
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
        e.addSeparator()
        for text, key, default in [("Ergebnisse &DIN-runden", "results/din", True),
                                   ("Unsicherheit relativ in &%", "results/pct", False)]:
            a = e.addAction(text, lambda on, k=key: (settings().setValue(k, on), self.show_stats(*self.stats)))
            a.setCheckable(True)
            a.setChecked(settings().value(key, default, type=bool))
        e.addMenu(self.copy_menu())
        t = self.menuBar().addMenu("&Tabelle")
        t.addAction("&Neue Tabelle", QKeySequence("Ctrl+Shift+T"), lambda: self.page_view().add_table())
        t.addAction("Tabelle &löschen", lambda: (v := self.table_view()) and self.page_view().remove_table(
            next(t for t in self.page_view().tiles if t.view is v)))
        t.addAction("&Y-Spalte hinzufügen", QKeySequence("Ctrl+Shift+Y"),
                    lambda: (v := self.table_view()) and v.model().add_y())
        t.addAction("Spalte &bearbeiten …", QKeySequence("Ctrl+Shift+E"),
                    lambda: (v := self.table_view()) and v.edit_column(v.currentIndex().column()))
        t.addAction("Spalte lö&schen", lambda: (v := self.table_view()) and v.model().remove_column(
            v.currentIndex().column()))
        t.addAction("Spalten&werte setzen …", QKeySequence("Ctrl+Shift+F"),
                    lambda: (v := self.table_view()) and v.set_values(v.currentIndex().column()))
        t.addAction("E&xportieren (CSV/xlsx/LaTeX) …", self.export_table)
        g = self.menuBar().addMenu("&Plot")
        g.addAction("Plot &anzeigen/ausblenden", QKeySequence("Ctrl+Shift+P"), lambda: self.page_view().toggle_plot())
        g.addAction("Achsen &tauschen x↔y", QKeySequence("Ctrl+Shift+X"), lambda: self.page_view().plot.swap())
        g.addAction("&Einstellungen (Achsen, Fits)", QKeySequence("Ctrl+Shift+A"),
                    lambda: self.page_view().show_settings())
        g.addAction("&Exportieren …", QKeySequence("Ctrl+E"), lambda: self.page_view().plot.export())
        g.addAction("&Python-Skript exportieren …", self.export_script)
        g.addAction("&Fit …", QKeySequence("Ctrl+Shift+G"),
                    lambda: (v := self.table_view()) and v.fit(v.currentIndex().column()))
        g.addSeparator()
        g.addAction("Plot-&Stil (Projekt) …", lambda: edit_style(self.project, self.stack, self, self.redraw_all))
        s = self.menuBar().addMenu("&Seite")
        s.addAction("&Hinzufügen", QKeySequence("Ctrl+T"), self.add_page)
        s.addAction("&Umbenennen …", QKeySequence("F2"), lambda: self.rename_page(self.tabs.currentIndex()))
        s.addAction("&Löschen", QKeySequence("Ctrl+W"), lambda: self.delete_page(self.tabs.currentIndex()))

        self.set_project(Project(), None)

    # --- Statistik & Ausgabe ---
    def show_stats(self, d: dict, unit: str):
        self.stats = (d, unit)
        self.stats_label.setText(summary(d, unit=unit, **result_opts()))

    def copy_menu(self) -> QMenu:
        m = QMenu("Statistik &kopieren", self)
        for text, tex in [("als &Text", False), ("als &siunitx", True)]:
            m.addAction(text, lambda t=tex: QApplication.clipboard().setText(
                summary(self.stats[0], unit=self.stats[1], tex=t, **result_opts())))
        return m

    def _save_name(self, title: str, filters: str) -> str:
        f, _ = QFileDialog.getSaveFileName(self, title, "", filters)
        return f

    def export_table(self):
        v = self.table_view()
        if v is None:
            return
        t = v.model().table
        f = self._save_name("Tabelle exportieren", "CSV (*.csv);;Excel, alle Tabellen der Seite (*.xlsx);;"
                                                   "LaTeX/siunitx (*.tex)")
        if not f:
            return
        try:
            if f.lower().endswith(".xlsx"):
                export.write_xlsx(self.page_view().page.tables, f)
            elif f.lower().endswith(".tex"):
                Path(f).write_text(export.latex_table(t, result_opts()["rounded"]), encoding="utf-8")
            else:
                export.write_csv(t, f)
        except OSError as e:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(e))

    def export_script(self):
        f = self._save_name("Python-Skript exportieren", "Python (*.py)")
        if f:
            try:
                Path(f).write_text(export.python_script(self.page_view().page, self.project.style), encoding="utf-8")
            except OSError as e:
                QMessageBox.critical(self, "Export fehlgeschlagen", str(e))

    def export_project(self):
        d = QFileDialog.getExistingDirectory(self, "Zielordner für den Projekt-Export")
        if not d:
            return
        name = self.path.stem if self.path else "Unbenannt"
        root = Path(d) / f"{export.safe_name(name)}_Export"
        if root.exists() and QMessageBox.question(
                self, "Projekt exportieren", f"{root.name} existiert. Dateien darin überschreiben?") != QMessageBox.Yes:
            return
        try:
            export.export_project(self.project, name, d)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(e))
            return
        self.statusBar().showMessage(f"Exportiert nach {root.name}", 5000)

    def redraw_all(self):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).plot.redraw()

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
            self.tabs.addTab(self._page_view(p), p.title)
        self.dirty = False
        self._update_title()

    def _page_view(self, p: Page) -> PageView:
        pv = PageView(p, self.project, self.stack)
        pv.panel.after_style = self.redraw_all
        pv.changed.connect(self._changed)
        return pv

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
        self.tabs.setCurrentIndex(self.tabs.addTab(self._page_view(p), p.title))
        self._changed()

    def rename_page(self, i: int):
        if i < 0:
            return
        p = self.project.pages[i]
        title, ok = QInputDialog.getText(self, "Seite umbenennen", "Titel:", text=p.title)
        if ok and title.strip() and title.strip() != p.title:
            p.title = title.strip()
            self.tabs.setTabText(i, p.title)
            self.tabs.widget(i).plot.redraw()  # Seitentitel über dem Plot
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
