"""Headless: Fenster baut, Seitenoperationen halten Modell und Tabs synchron, Schriften laden lokal."""
import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from kurvenwerk import style  # noqa: E402
from kurvenwerk.mainwindow import MainWindow  # noqa: E402
from kurvenwerk.model import Project  # noqa: E402

app = QApplication.instance() or QApplication([])


def test_style_fonts_loaded():
    style.apply(app)
    fams = QFontDatabase.families()
    assert "Manrope" in fams and "IBM Plex Mono" in fams
    assert "$" not in style.stylesheet(True) and "$" not in style.stylesheet(False)


def test_pages_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    w = MainWindow()
    w.add_page()
    w.add_page()
    assert w.tabs.count() == len(w.project.pages) == 3 and w.dirty
    w.delete_page(1)
    assert [p.title for p in w.project.pages] == ["Seite 1", "Seite 3"]
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == ["Seite 1", "Seite 3"]
    w.delete_page(0)
    w.delete_page(0)  # letzte Seite bleibt
    assert w.tabs.count() == 1
    w.path = tmp_path / "p.kwproj"
    assert w.save() and not w.dirty
    assert Project.load(w.path) == w.project


def test_layout_collapsible_and_remembered(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from kurvenwerk import mainwindow
    ini = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    monkeypatch.setattr(mainwindow, "settings", lambda: ini)  # nicht in die echte Registry schreiben
    w = MainWindow()
    w.resize(1200, 750)
    w.show()
    pv = w.page_view()
    assert pv.count() == 2 and pv.top.count() == 3  # Tabellen | Plot | Panel, darunter Auswertung
    assert all(s.childrenCollapsible() for s in pv.splitters().values())
    pv.top.setSizes([0, 800, 300])  # Tabellen ganz zugeklappt
    pv.save_layout()
    w.add_page()  # neue Seite übernimmt das Layout beim Anzeigen
    app.processEvents()
    assert w.page_view().top.sizes()[0] == 0 and w.page_view().plot.isVisible()
    w.hide()


def test_plot_live_update_and_undo():
    w = MainWindow()
    pv = w.page_view()
    m = pv.tiles[0].model
    m.set_cells({(0, 0): 1.0, (0, 1): 2.0, (1, 0): 2.0, (1, 1): 5.0}, "Werte")
    app.processEvents()  # Timer bündelt die Signale → ein Neuzeichnen
    ax = pv.plot.canvas.figure.axes[0]
    assert list(ax.lines[0].get_ydata()) == [2.0, 5.0] and ax.get_xlabel() == "x"
    pv.plot.swap()
    assert pv.page.plot == {"swap": True} and pv.plot.canvas.figure.axes[0].get_xlabel() == "y"
    m.set_style(1, {"axis": "y2"})
    app.processEvents()
    assert len(pv.plot.canvas.figure.axes) == 2
    pv.toggle_plot()
    assert not pv.page.show_plot and pv.plot.isHidden()
    w.stack.undo()
    w.stack.undo()
    w.stack.undo()
    app.processEvents()
    assert pv.page.show_plot and pv.page.plot == {} and m.table.columns[1].style == {}
    assert pv.plot.canvas.figure.axes[0].get_xlabel() == "x"


def test_fit_click_excludes_point_and_dialog():
    from types import SimpleNamespace

    from kurvenwerk.fitview import FitDialog
    from kurvenwerk.plot import series
    w = MainWindow()
    pv = w.page_view()
    m = pv.tiles[0].model
    m.set_cells({(r, c): float(r + 1 if c == 0 else 2 * r + 3) for r in range(4) for c in range(2)}, "Werte")
    m.set_fit(1, {"formula": "a*x + b"})
    app.processEvents()
    a, s, x, y = pv.plot.drawn[0]
    px, py = a.transData.transform((x[2], y[2]))
    pv.plot.click(SimpleNamespace(button=1, dblclick=False, x=px + 3, y=py))
    assert m.table.columns[1].fit == {"formula": "a*x + b", "excluded": [2]}
    app.processEvents()
    d = FitDialog(series(m.table)[0])
    assert d.values()["excluded"] == [2] and d.params.rowCount() == 2
    d.preview()
    assert d.result is not None and np.allclose(d.result.values, [2, 1])
    w.stack.undo()
    assert m.table.columns[1].fit == {"formula": "a*x + b"}


def test_selection_stats_and_fit_report():
    from PySide6.QtCore import QItemSelection, QItemSelectionModel
    from kurvenwerk import plot
    from kurvenwerk.fitview import FitDialog
    w = MainWindow()
    v = w.page_view().tiles[0].view
    m = v.model()
    m.set_cells({(i, j): float(i + 1) * (j + 1) + (0.1 if j and i % 2 else 0) for i in range(4) for j in (0, 1)}, "W")
    v.selectionModel().select(QItemSelection(m.index(0, 1), m.index(3, 1)), QItemSelectionModel.ClearAndSelect)
    assert w.stats[0]["n"] == 4 and "n = 4" in w.stats_label.text()
    m.table.columns[1].fit = {"formula": "a*x + b"}
    d = FitDialog(plot.series(m.table)[0], v)
    d.preview()
    assert "R²" in d.msg.text() and "adj. R²" in d.msg.text()


def test_panel_fit_formula_and_axes():
    w = MainWindow()
    pv = w.page_view()
    m = pv.tiles[0].model
    m.set_cells({(r, c): float(r + 1 if c == 0 else 2 * (r + 1) ** 2 + 3) for r in range(4) for c in range(2)}, "Werte")
    app.processEvents()
    row = pv.panel.rows[0]
    row.formula.setText("a*x^2 + b")
    assert "Parameter: a, b" in row.result.text()
    row.commit()
    app.processEvents()
    assert m.table.columns[1].fit == {"formula": "a*x^2 + b"} and "a = 2" in pv.panel.rows[0].result.text()
    pv.panel.rows[0].line.setChecked(True)
    assert m.table.columns[1].fit == {"formula": "a*x + b"}
    w.stack.undo()
    w.stack.undo()
    app.processEvents()
    assert m.table.columns[1].fit == {} and pv.panel.rows[0].result.text() == "kein Fit"
    e = pv.panel.edits["xmax"][0]
    e.setText("abc")
    pv.panel.commit("xmax")
    assert pv.page.plot == {} and pv.panel.msg.text()
    e.setText("10")
    pv.panel.commit("xmax")
    pv.panel.checks["ylog"].setChecked(True)
    assert pv.page.plot == {"xmax": 10.0, "ylog": True}
    pv.panel.checks["grid"].setChecked(not pv.panel.checks["grid"].isChecked())
    assert "grid" in w.project.style and w.stack.undo() is None and w.project.style == {}
    pv.panel.checks["grid"].setChecked(False)
    assert not pv.plot.canvas.figure.axes[0].xaxis.get_gridlines()[0].get_visible()
