"""Headless: Tabellenmodell, Excel-Navigation, Paste, Undo/Redo."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kurvenwerk.mainwindow import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])


def window():
    for o in QApplication.topLevelWidgets():
        o.hide()  # alte Testfenster stehlen sonst die Aktivierung
    w = MainWindow()
    w.show()
    w.activateWindow()
    assert QTest.qWaitForWindowActive(w)  # sonst kein Fokus im Offscreen-Betrieb
    pv = w.page_view()
    pv.add_table()  # zweite Kachel
    return w, pv, pv.tiles[0].view, pv.tiles[1].view


def cur(v):
    return v.currentIndex().row(), v.currentIndex().column()


def type_cell(v, text, key):
    QTest.keyClick(v, text[0])  # startet Editor (AnyKeyPressed), Rest geht an den Editor
    QTest.keyClicks(QApplication.focusWidget(), text[1:])
    QTest.keyClick(QApplication.focusWidget(), key)


def test_excel_entry_tab_enter_and_undo():
    w, pv, v, v2 = window()
    v.setFocus()
    v.setCurrentIndex(v.model().index(0, 0))
    type_cell(v, "1,5", Qt.Key_Tab)
    type_cell(v, "2", Qt.Key_Return)
    assert cur(v) == (1, 0)  # Enter springt in die Startspalte der Tab-Folge
    type_cell(v, "3", Qt.Key_Tab)
    type_cell(v, "4e-3", Qt.Key_Return)
    t = pv.page.tables[0]
    assert [c.values for c in t.columns] == [[1.5, 3.0], [2.0, 0.004]]
    assert w.dirty
    w.stack.undo()
    w.stack.undo()
    assert [c.values for c in t.columns] == [[1.5], [2.0]]
    w.stack.redo()
    assert t.columns[0].values == [1.5, 3.0]
    type_cell(v, "abc", Qt.Key_Return)  # keine Zahl → verworfen
    assert t.columns[0].values == [1.5, 3.0]


def test_tile_switch_by_keyboard():
    w, pv, v, v2 = window()
    for m in (v.model(), v2.model()):
        m.set_cells({(3, 0): 1.0}, "Werte")  # Zeilen bis 4 genutzt
    v.setFocus()
    v.setCurrentIndex(v.model().index(3, 1))
    QTest.keyClick(v, Qt.Key_Tab)  # letzte Spalte → Nachbarkachel
    assert v2.hasFocus() and cur(v2) == (3, 0)
    QTest.keyClick(v2, Qt.Key_Backtab)  # zurück in die letzte Spalte
    assert v.hasFocus() and cur(v) == (3, 1)
    QTest.keyClick(v, Qt.Key_F6)
    assert v2.hasFocus() and cur(v2) == (3, 1)
    QTest.keyClick(v2, Qt.Key_F6)  # rechter Rand: bleibt
    assert v2.hasFocus()
    QTest.keyClick(v2, Qt.Key_F6, Qt.ShiftModifier)
    assert v.hasFocus()


def test_paste_header_extends_columns_single_undo():
    w, pv, v, v2 = window()
    m = v.model()
    m.paste("U / mV\tI [µA]\tΔI / µA\tΔU / mV\n0,5\t1\t0,1\t0,01\n1\t2\t0,1\t0,01", 2, 0, "auto")
    cols = pv.page.tables[0].columns
    assert [(c.name, c.unit, c.role) for c in cols] == [
        ("U", "mV", "X"), ("I", "µA", "Y"), ("ΔI", "µA", "Δy"), ("ΔU", "mV", "Δx")]
    assert cols[0].values == [None, None, 0.5, 1.0] and cols[3].values == [None, None, 0.01, 0.01]
    assert m.columnCount() == 4 and m.headerData(0, Qt.Horizontal) == "U / mV\nX"
    w.stack.undo()
    assert [c.name for c in cols] != ["U"] and len(pv.page.tables[0].columns) == 2


def test_columns_roles_and_add_table_undo():
    w, pv, v, v2 = window()
    m = v.model()
    m.add_y()
    m.set_column(2, "t", "s", "X")  # nur ein X pro Tabelle
    assert [c.role for c in m.table.columns] == ["Y", "Y", "X"]
    m.remove_column(0)
    assert m.columnCount() == 2
    assert len(pv.page.tables) == len(pv.tiles) == 2
    while w.stack.canUndo():
        w.stack.undo()
    assert len(pv.page.tables) == len(pv.tiles) == 1
    assert [c.name for c in m.table.columns] == ["x", "y"]
    while w.stack.canRedo():
        w.stack.redo()
    assert len(pv.tiles) == 2 and [c.role for c in m.table.columns] == ["Y", "X"]


def test_formula_column_scale_and_cell_formula():
    w, pv, v, v2 = window()
    m = v.model()
    m.paste("U / mV\tI / mA\tΔU / mV\n2\t3\t0,1\n4\t5\t0,1", 0, 0, "auto")
    m.add_y()
    m.set_formula(3, "U*I", True)  # Spalte P → ΔP wird angelegt, ΔI fehlt → nur U-Anteil
    assert [c.name for c in m.table.columns] == ["U", "I", "ΔU", "y3", "Δy3"]
    assert m.table.columns[3].values == [6.0, 20.0] and m.table.columns[4].values == pytest.approx([0.3, 0.5])
    assert not m.flags(m.index(0, 3)) & Qt.ItemIsEditable
    m.set_cells({(1, 0): 10.0}, "Zelle ändern")  # Quelle ändern → live neu berechnet
    assert m.table.columns[3].values == [6.0, 50.0]
    m.scale(0, 1e-3, "V")  # mV → V, ΔU zieht mit
    assert m.table.columns[0].values == [0.002, 0.01] and (m.table.columns[2].unit, m.table.columns[2].values) == ("V", [1e-4, 1e-4])
    assert m.table.columns[3].values == pytest.approx([0.006, 0.05])
    assert m.setData(m.index(2, 1), "=2*i+1") and m.table.columns[1].values[2] == 7.0
    assert not m.setData(m.index(2, 1), "=os")
    w.stack.undo()
    w.stack.undo()
    assert m.table.columns[0].values == [2.0, 10.0]
    while w.stack.canUndo():
        w.stack.undo()
    assert [c.name for c in m.table.columns] == ["x", "y"]


def test_rows_grow_with_data_and_enter_in_last_row():
    w, pv, v, v2 = window()
    m = v.model()
    assert m.rowCount() == 1  # leer: nur eine Eingabezeile
    v.setFocus()
    v.setCurrentIndex(m.index(0, 0))
    type_cell(v, "1", Qt.Key_Return)
    assert m.rowCount() == 2 and cur(v) == (1, 0)  # Enter in der letzten Zeile → neue leere Zeile
    type_cell(v, "2", Qt.Key_Return)
    assert m.rowCount() == 3 and cur(v) == (2, 0)
    m.set_cells({(0, 0): None}, "leeren")
    assert m.rowCount() == 3  # Lücke oben bleibt
    m.set_cells({(1, 0): None}, "leeren")
    assert m.rowCount() == 1  # alles leer → nur Eingabezeile
    w.stack.undo()
    assert m.rowCount() == 3
    m.paste("1\n2\n3\n4\n5", 2, 1, "auto")
    assert m.rowCount() == 8


def test_remove_table_undo_keeps_order():
    w, pv, v, v2 = window()
    pv.add_table()
    t0, t1, t2 = pv.page.tables
    pv.remove_table(pv.tiles[1])
    assert pv.page.tables == [t0, t2] and [t.model.table for t in pv.tiles] == [t0, t2]
    pv.remove_table(pv.tiles[0])
    pv.remove_table(pv.tiles[0])
    assert pv.page.tables == [] and pv.tiles == []
    while w.stack.canUndo():
        w.stack.undo()
    assert len(pv.page.tables) == 1  # bis vor die beiden add_table
    for _ in range(3):  # 2× hinzufügen, mittlere löschen
        w.stack.redo()
    assert pv.page.tables == [t0, t2]
    w.stack.undo()
    assert [t.model.table for t in pv.tiles] == [t0, t1, t2]
    assert all(a is b for a, b in zip(pv.page.tables, (t0, t1, t2)))


def test_remove_x_and_gauss_error_column():
    w = MainWindow()  # ohne Fokus
    m = w.page_view().tiles[0].model
    m.paste("U\tI\tΔU\n2\t3\t0,1", 0, 0, "auto")
    m.add_y()
    m.set_formula(3, "U*I", True)
    assert [c.name for c in m.table.columns] == ["U", "I", "ΔU", "y3", "Δy3"]
    m.remove_column(4)  # Gauß-Δ: bleibt weg, Formel rechnet ohne Fehler weiter
    assert [c.name for c in m.table.columns] == ["U", "I", "ΔU", "y3"] and not m.table.columns[3].gauss
    m.remove_column(0)  # X-Spalte
    assert [c.role for c in m.table.columns] == ["Y", "Δx", "Y"]
    m.remove_column(9)  # außerhalb: nichts
    w.stack.undo()
    w.stack.undo()
    assert [c.name for c in m.table.columns] == ["U", "I", "ΔU", "y3", "Δy3"]


def test_swap_columns_moves_errors_roles_stay():
    w = MainWindow()
    m = w.page_view().tiles[0].model
    m.paste("U\tΔU\tI\tΔI\tP\n1\t0,1\t2\t0,2\t3", 0, 0, "auto")
    m.set_column(1, "ΔU", "", "Δx")  # bestehende 2. Spalte bekommt beim Paste keine Δ-Rolle
    m.set_column(2, "I", "", "Y")
    cols = lambda: [(c.name, c.role) for c in m.table.columns]  # noqa: E731
    assert cols() == [("U", "X"), ("ΔU", "Δx"), ("I", "Y"), ("ΔI", "Δy"), ("P", "Y")]
    m.swap_columns(0, 2)  # I wird X, U wird Y; Fehler wandern mit
    assert cols() == [("I", "X"), ("ΔI", "Δx"), ("U", "Y"), ("ΔU", "Δy"), ("P", "Y")]
    assert m.table.columns[1].values == [0.2]
    m.swap_columns(2, 4)
    assert cols() == [("I", "X"), ("ΔI", "Δx"), ("P", "Y"), ("U", "Y"), ("ΔU", "Δy")]
    m.swap_columns(0, 1)  # Δ-Spalte: nichts
    w.stack.undo()
    w.stack.undo()
    assert cols()[0] == ("U", "X")


def test_table_title_rename_undo():
    w = MainWindow()
    tile = w.page_view().tiles[0]
    tile.title.setText("Kennlinie")
    tile.rename()
    assert tile.model.table.name == "Kennlinie"
    w.stack.undo()
    assert tile.model.table.name == tile.title.text() != "Kennlinie"
