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
