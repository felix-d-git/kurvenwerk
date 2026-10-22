"""Headless: Fenster baut, Seitenoperationen halten Modell und Tabs synchron, Schriften laden lokal."""
import os

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
