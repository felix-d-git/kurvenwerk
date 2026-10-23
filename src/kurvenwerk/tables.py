"""Tabellen-Kachel: Modell über model.Table, Excel-artige Navigation, Paste, Undo per Snapshot."""
from copy import deepcopy

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSettings, Qt, Signal
from PySide6.QtGui import QKeySequence, QUndoCommand
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMenu, QMessageBox, QTableView, QToolButton, QVBoxLayout,
                               QWidget)

from .formula import FUNCS, ROW, FormulaError, error_column, number, parse, prefix_factor, recompute, row_value
from .model import ROLES, Column, Table
from .paste import parse, to_float
from .plotview import series_style



def settings() -> QSettings:
    return QSettings("Kurvenwerk", "Kurvenwerk")


def paste_decimal() -> str:
    v = settings().value("paste/decimal", "auto")
    return v if v in ("auto", ".", ",") else "auto"


def result_opts() -> dict:
    """Ausgabe von Ergebnissen: DIN-Rundung, Unsicherheit relativ in %."""
    s = settings()
    return {"rounded": s.value("results/din", True, type=bool), "pct": s.value("results/pct", False, type=bool)}


def _rows(cols: list[Column]) -> int:
    """Genutzte Zeilen + 1 leere zum Weitertippen."""
    return max((len(c.values) for c in cols), default=0) + 1


def _tidy(cols: list[Column]) -> None:
    for c in cols:
        while c.values and c.values[-1] is None:
            c.values.pop()


class TableCmd(QUndoCommand):
    # ponytail: Snapshot der ganzen Tabelle pro Schritt; Diff-Kommandos, falls Tabellen sehr groß werden
    def __init__(self, model: "TableModel", old: list[Column], new: list[Column], text: str):
        super().__init__(text)
        self.model, self.old, self.new = model, old, new

    def redo(self):
        self.model.apply(self.new)

    def undo(self):
        self.model.apply(self.old)


class TableModel(QAbstractTableModel):
    def __init__(self, table: Table, stack):
        super().__init__()
        self.table, self.stack = table, stack

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else _rows(self.table.columns)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.table.columns)

    def _value(self, i: QModelIndex):
        vals = self.table.columns[i.column()].values
        return vals[i.row()] if i.row() < len(vals) else None

    def data(self, i, role=Qt.DisplayRole):
        if role in (Qt.DisplayRole, Qt.EditRole):
            v = self._value(i)
            return "" if v is None else format(v, ".15g")
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def flags(self, i):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return f if self.table.columns[i.column()].formula else f | Qt.ItemIsEditable

    def headerData(self, s, orient, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orient == Qt.Vertical:
            return str(s + 1)
        c = self.table.columns[s]
        role = f"{c.role}  = {c.formula}" if c.formula else c.role
        return f"{c.name} / {c.unit}\n{role}" if c.unit else f"{c.name}\n{role}"

    def setData(self, i, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        text = str(value).strip()
        if text.startswith("="):  # Zellformel: einmal ausrechnen, Zahl speichern
            try:
                v = row_value(text[1:], self.table.columns, i.row())
            except FormulaError:
                return False
        else:
            v = to_float(text) if text else None
        if text and v is None:
            return False  # keine Zahl → Eingabe verwerfen
        if v != self._value(i):
            self.set_cells({(i.row(), i.column()): v}, "Zelle ändern")
        return True

    # --- Änderungen (alle über den Undo-Stack) ---
    def edit(self, fn, text: str) -> None:
        cols = deepcopy(self.table.columns)
        fn(cols)
        recompute(cols)
        _tidy(cols)
        if cols != self.table.columns:
            self.stack.push(TableCmd(self, deepcopy(self.table.columns), cols, text))

    def set_cells(self, cells: dict[tuple[int, int], float | None], text: str) -> None:
        def fn(cols):
            for (r, c), v in cells.items():
                vals = cols[c].values
                vals.extend([None] * (r + 1 - len(vals)))
                vals[r] = v
        self.edit(fn, text)

    def apply(self, cols: list[Column]) -> None:
        rows, ncols = self.rowCount(), self.columnCount()
        if len(cols) != ncols:
            self.beginResetModel()
            self.table.columns = deepcopy(cols)
            self.endResetModel()
            return
        new_rows = _rows(cols)
        if new_rows > rows:
            self.beginInsertRows(QModelIndex(), rows, new_rows - 1)
        elif new_rows < rows:
            self.beginRemoveRows(QModelIndex(), new_rows, rows - 1)
        self.table.columns = deepcopy(cols)
        if new_rows > rows:
            self.endInsertRows()
        elif new_rows < rows:
            self.endRemoveRows()
        if ncols:
            self.dataChanged.emit(self.index(0, 0), self.index(new_rows - 1, ncols - 1))
            self.headerDataChanged.emit(Qt.Horizontal, 0, ncols - 1)

    def paste(self, text: str, row: int, col: int, decimal: str) -> None:
        headers, data = parse(text, decimal)
        if not data:
            return

        def fn(cols):
            for j, vals in enumerate(data):
                if col + j >= len(cols):
                    cols.append(Column(f"y{len(cols)}"))
                c = cols[col + j]
                if headers and headers[j][0]:
                    c.name, c.unit = headers[j]
                    if col + j >= len(self.table.columns) and c.name.startswith("Δ"):
                        x = next((k.name for k in cols if k.role == "X"), None)
                        c.role = "Δx" if c.name[1:] == x else "Δy"
                c.values.extend([None] * (row + len(vals) - len(c.values)))
                c.values[row:row + len(vals)] = vals
        self.edit(fn, "Einfügen")

    def set_column(self, j: int, name: str, unit: str, role: str) -> None:
        def fn(cols):
            if role == "X":  # ein X pro Tabelle
                for c in cols:
                    if c.role == "X":
                        c.role = "Y"
            cols[j].name, cols[j].unit, cols[j].role = name, unit, role
        self.edit(fn, "Spalte bearbeiten")

    def set_formula(self, j: int, formula: str, gauss: bool) -> None:
        """Leere Formel → Spalte wird wieder normale Datenspalte, Werte bleiben stehen."""
        def fn(cols):
            cols[j].formula, cols[j].gauss = formula, gauss and bool(formula)
        self.edit(fn, "Spaltenwerte setzen")

    def scale(self, j: int, k: float, unit: str | None = None) -> None:
        """Spalte (und ihr Δ) × k; bei Formelspalten wird die Formel erweitert."""
        def fn(cols):
            c = cols[j]
            e = error_column(cols, c.name)
            for col in (c, e) if e and not c.formula else (c,):
                col.values = [None if v is None else v * k for v in col.values]
                if unit is not None and col is not c and col.unit == c.unit:
                    col.unit = unit
            if c.formula:
                c.formula = f"({c.formula})*{k!r}"
            if unit is not None:
                c.unit = unit
        self.edit(fn, "Einheit umrechnen" if unit is not None else "Spalte × Faktor")

    def set_style(self, j: int, style: dict) -> None:
        def fn(cols):
            cols[j].style = style
        self.edit(fn, "Reihen-Stil")

    def set_fit(self, j: int, fit: dict) -> None:
        def fn(cols):
            cols[j].fit = fit
        self.edit(fn, "Fit")

    def add_y(self) -> None:
        self.edit(lambda cols: cols.append(Column(f"y{len(cols)}")), "Y-Spalte hinzufügen")

    def remove_column(self, j: int) -> None:
        """Auch X; Δ einer Gauß-Formelspalte → deren Gauß aus, sonst legt recompute sie sofort neu an."""
        if not 0 <= j < self.columnCount() or self.columnCount() == 1:
            return

        def fn(cols):
            c = cols.pop(j)
            for k in cols:
                if k.gauss and c.name == "Δ" + k.name:
                    k.gauss = False
        self.edit(fn, "Spalte löschen")


class ColumnDialog(QDialog):
    def __init__(self, c: Column, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spalte")
        f = QFormLayout(self)
        self.name, self.unit = QLineEdit(c.name), QLineEdit(c.unit)
        self.role = QComboBox()
        self.role.addItems(ROLES)
        self.role.setCurrentText(c.role)
        f.addRow("Größe", self.name)
        f.addRow("Einheit", self.unit)
        f.addRow("Rolle", self.role)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        f.addRow(b)


class FormulaDialog(QDialog):
    """Spaltenwerte setzen: Formel aus Spaltennamen (Text, LaTeX oder $…$), optional Gauß-Fehler."""

    def __init__(self, cols: list[Column], j: int, parent=None):
        super().__init__(parent)
        c = cols[j]
        self.names = [k.name for k in cols]
        self.setWindowTitle(f"Spaltenwerte setzen – {c.name}")
        f = QFormLayout(self)
        self.text = QLineEdit(c.formula, placeholderText="z.B. U*I, \\frac{U}{I}, $U^2$")
        self.gauss = QCheckBox(f"Gauß-Fehler nach Δ{c.name} schreiben", checked=c.gauss or not c.formula)
        self.msg = QLabel(wordWrap=True)
        refs = ", ".join(n for n in self.names if n.isidentifier() and n != c.name)
        f.addRow("Formel", self.text)
        f.addRow(self.gauss)
        f.addRow(QLabel(f"Spalten: {refs or '–'} · Zeile: {ROW} · {', '.join(FUNCS)}, pi, e\n"
                        "Leer lassen = Formel entfernen, Werte bleiben.", wordWrap=True))
        f.addRow(self.msg)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.check)
        b.rejected.connect(self.reject)
        f.addRow(b)

    def check(self):
        try:
            if self.text.text().strip():
                parse(self.text.text(), self.names)
        except FormulaError as e:
            self.msg.setText(str(e))
            return
        self.accept()


class TableView(QTableView):
    """Tab/Shift+Tab → rechts/links (am Rand in die Nachbarkachel), Enter/Shift+Enter → runter/hoch
    zurück in die Spalte, in der die Tab-Folge begann (wie Excel). F6/Shift+F6 → Nachbarkachel."""
    tile = Signal(int, int, int)  # Richtung ±1, Zeile, Spalte (-1 = letzte)

    def __init__(self, model: TableModel):
        super().__init__()
        self.setModel(model)
        self.setAlternatingRowColors(True)
        self.origin = None  # Spalte, in der eine Tab-Folge begann
        h = self.horizontalHeader()
        h.sectionDoubleClicked.connect(self.edit_column)
        h.setContextMenuPolicy(Qt.CustomContextMenu)
        h.customContextMenuRequested.connect(lambda p: self.header_menu(h.logicalIndexAt(p)))
        self.verticalHeader().setDefaultSectionSize(24)

    def navigate(self, key, shift: bool) -> None:
        cur = self.currentIndex()
        r, c = (cur.row(), cur.column()) if cur.isValid() else (0, 0)
        if key == Qt.Key_Tab:
            if self.origin is None:
                self.origin = c
            c += -1 if shift else 1
            if not 0 <= c < self.model().columnCount():
                self.origin = None
                self.tile.emit(-1 if shift else 1, r, -1 if shift else 0)
                return
        else:  # Enter
            if self.state() == QAbstractItemView.EditingState and (ed := QApplication.focusWidget()) is not self:
                self.commitData(ed)  # erst übernehmen → neue leere Zeile existiert schon
            r = max(0, min(r + (-1 if shift else 1), self.model().rowCount() - 1))
            c, self.origin = (c if self.origin is None else self.origin), None
        self.setCurrentIndex(self.model().index(r, c))

    def keyPressEvent(self, e):
        shift = bool(e.modifiers() & Qt.ShiftModifier)
        if e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.navigate(Qt.Key_Tab, shift or e.key() == Qt.Key_Backtab)
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.navigate(Qt.Key_Return, shift)
        elif e.key() == Qt.Key_F6:
            cur = self.currentIndex()
            self.tile.emit(-1 if shift else 1, max(cur.row(), 0), max(cur.column(), 0))
        elif e.matches(QKeySequence.Paste):
            self.paste()
        elif e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.model().set_cells({(i.row(), i.column()): None for i in self.selectedIndexes()},
                                   "Zellen leeren")
        else:
            if not e.text() and e.key() not in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt):
                self.origin = None  # Pfeiltasten u. Ä. beenden die Tab-Folge, Tippen nicht
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        self.origin = None
        super().mousePressEvent(e)

    def closeEditor(self, editor, hint):
        # Tab schluckt der Delegate und meldet EditNext/PreviousItem; Enter läuft als Tastendruck
        # bis keyPressEvent durch (Wechsel der Zelle schließt den Editor mit Übernahme).
        nav = {QAbstractItemDelegate.EditNextItem: False, QAbstractItemDelegate.EditPreviousItem: True}.get(hint)
        super().closeEditor(editor, QAbstractItemDelegate.NoHint if nav is not None else hint)
        if nav is not None:
            self.navigate(Qt.Key_Tab, nav)

    def paste(self):
        cur = self.currentIndex()
        r, c = (cur.row(), cur.column()) if cur.isValid() else (0, 0)
        self.model().paste(QApplication.clipboard().text(), r, c, paste_decimal())

    def edit_column(self, j: int):
        if j < 0:
            return
        d = ColumnDialog(self.model().table.columns[j], self)
        if d.exec():
            self.model().set_column(j, d.name.text().strip(), d.unit.text().strip(), d.role.currentText())

    def set_values(self, j: int):
        if j < 0:
            return
        d = FormulaDialog(self.model().table.columns, j, self)
        if d.exec():
            self.model().set_formula(j, d.text.text().strip(), d.gauss.isChecked())

    def multiply(self, j: int):
        text, ok = QInputDialog.getText(self, "Spalte × Faktor", "Faktor (z.B. 2, 1e-3, 1/3, pi):")
        if not ok or not text.strip():
            return
        try:
            self.model().scale(j, number(text))
        except FormulaError as e:
            QMessageBox.warning(self, "Spalte × Faktor", str(e))

    def convert_unit(self, j: int):
        old = self.model().table.columns[j].unit
        new, ok = QInputDialog.getText(self, "Einheit umrechnen", f"Neue Einheit (statt {old or '–'}):", text=old)
        if not ok or new.strip() == old:
            return
        k = prefix_factor(old, new.strip())
        if k is None:
            QMessageBox.warning(self, "Einheit umrechnen",
                                f"{old or '–'} → {new.strip()}: nur SI-Präfixe derselben Einheit (mV → V, cm² → m²).")
            return
        self.model().scale(j, k, new.strip())

    def selectionChanged(self, sel, desel):
        super().selectionChanged(sel, desel)
        if hasattr(w := self.window(), "show_stats"):
            w.show_stats(*self.selection_stats())

    def selection_stats(self) -> tuple[dict, str]:
        """Statistik der markierten Zellen (ab 2). Nur eine Spalte → deren Einheit und Δ-Spalte (gewichteter Mittelwert)."""
        from . import plot
        from .stats import describe
        idx = self.selectedIndexes()
        if len(idx) < 2:
            return {"n": 0}, ""
        m, cols = self.model(), self.model().table.columns
        val = lambda i: float("nan") if (v := m._value(i)) is None else v  # noqa: E731
        x = [val(i) for i in idx]
        js = {i.column() for i in idx}
        if len(js) > 1:
            return describe(x), ""
        j = js.pop()
        e = plot._error(cols, j) if cols[j].role in ("X", "Y") else None
        je = next((k for k, c in enumerate(cols) if c is e), None)
        dx = None if je is None else [abs(val(m.index(i.row(), je))) for i in idx]
        return describe(x, dx), cols[j].unit

    def series_style(self, j: int):
        v = series_style(self.model().table.columns[j].style, self)
        if v is not None:
            self.model().set_style(j, v)

    def fit(self, j: int):
        """Fit-Dialog für Spalte j; ist sie keine Y-Spalte, die erste Y-Spalte."""
        from . import plot
        from .fitview import FitDialog  # lazy: fitview → plot, tables → plotview
        cols = self.model().table.columns
        if j < 0 or cols[j].role != "Y":
            j = next((k for k, c in enumerate(cols) if c.role == "Y"), -1)
        s = next((s for s in plot.series(self.model().table) if j >= 0 and s.ycol is cols[j]), None)
        if s is None:
            QMessageBox.information(self, "Fit", "Keine Y-Spalte mit Daten (X und Y) in dieser Tabelle.")
            return
        d = FitDialog(s, self)
        if d.exec() and d.result_fit != cols[j].fit:
            self.model().set_fit(j, d.result_fit)

    def header_menu(self, j: int):
        m = QMenu(self)
        if j >= 0:
            m.addAction("Spalte bearbeiten …", lambda: self.edit_column(j))
            m.addAction("Spaltenwerte setzen …", lambda: self.set_values(j))
            m.addAction("Spalte × Faktor …", lambda: self.multiply(j))
            m.addAction("Einheit umrechnen …", lambda: self.convert_unit(j))
            if self.model().table.columns[j].role == "Y":
                m.addAction("Reihen-Stil …", lambda: self.series_style(j))
                m.addAction("Fit …", lambda: self.fit(j))
            m.addAction("Spalte löschen", lambda: self.model().remove_column(j))
        m.addAction("Y-Spalte hinzufügen", self.model().add_y)
        m.exec(self.cursor().pos())


class TableTile(QWidget):
    """Kachel: Titelzeile (Name, + Y, ✕) über der Tabelle."""
    remove = Signal()

    def __init__(self, table: Table, stack):
        super().__init__()
        self.setObjectName("page")
        self.model = TableModel(table, stack)
        self.view = TableView(self.model)
        top = QHBoxLayout()
        top.addWidget(QLabel(table.name))
        top.addStretch()
        add = QToolButton(text="+ Y", toolTip="Y-Spalte hinzufügen")
        add.clicked.connect(self.model.add_y)
        top.addWidget(add)
        rm = QToolButton(text="✕", toolTip="Tabelle löschen (Strg+Z holt sie zurück)")
        rm.clicked.connect(self.remove)
        top.addWidget(rm)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.view)


class AddTableCmd(QUndoCommand):
    """Kachel bleibt über Undo/Redo dasselbe Objekt → spätere TableCmds zeigen weiter aufs richtige Modell."""

    def __init__(self, page_view, table: Table):
        super().__init__("Tabelle hinzufügen")
        self.pv, self.tile = page_view, TableTile(table, page_view.stack)

    def redo(self):
        self.pv.insert_tile(self.tile)

    def undo(self):
        self.pv.remove_tile(self.tile)


class RemoveTableCmd(QUndoCommand):
    """Kachel samt Tabelle raus; Undo setzt dasselbe Objekt an alter Stelle wieder ein."""

    def __init__(self, page_view, tile: TableTile):
        super().__init__("Tabelle löschen")
        self.pv, self.tile, self.i = page_view, tile, page_view.tiles.index(tile)

    def redo(self):
        self.pv.remove_tile(self.tile)

    def undo(self):
        self.pv.insert_tile(self.tile, self.i)
