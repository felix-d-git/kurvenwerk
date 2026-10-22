"""Plot-Logik headless: Reihen/Fehler-Zuordnung, Achsen tauschen, 2. y-Achse, Log, Grenzen, Export-Größe."""
import shutil

import numpy as np
import pytest
from matplotlib.figure import Figure

from kurvenwerk.model import Column, Page, Table
from kurvenwerk.plot import draw, export, label_error, safe, series


def page(**plot) -> Page:
    t = Table("T", [
        Column("U", "V", "X", [1.0, 2.0, None, 4.0]),
        Column("ΔU", "V", "Δx", [0.1, 0.1, 0.1, 0.2]),
        Column("I", "mA", "Y", [10.0, 20.0, 30.0, 40.0]),
        Column("dI", "mA", "Δy", [1.0, -2.0, 3.0]),  # Δ-Spalte rechts daneben, Name passt nicht
        Column("P", "mW", "Y", [10.0, 40.0, 90.0, None], style={"axis": "y2", "label": "$P$"}),
    ])
    return Page("S", [t], plot=plot)


def test_series_pairs_errors_and_drops_gaps():
    s = series(page().tables[0])
    assert [c.ycol.name for c in s] == ["I", "P"]
    np.testing.assert_array_equal(s[0].x, [1, 2, 4])
    np.testing.assert_array_equal(s[0].dx, [0.1, 0.1, 0.2])
    np.testing.assert_array_equal(s[0].dy, [1, 2, 0])  # fehlender Fehler → 0, negativer → Betrag
    np.testing.assert_array_equal(s[1].y, [10, 40])
    assert s[1].dy is None
    assert series(Table("leer", [Column("y", "", "Y", [1.0])])) == []


def test_draw_axes_labels_y2():
    fig = Figure()
    draw(fig, page(ylog=True, xmin=0, xmax=5, title="Kennlinie"), {})
    ax, ax2 = fig.axes
    assert ax.get_xlabel() == "U / V" and ax.get_ylabel() == "I / mA" and ax2.get_ylabel() == "P / mW"
    assert ax.get_yscale() == "log" and ax.get_xlim() == (0, 5)
    assert ax.get_title() == "Kennlinie"
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ["I / mA", "$P$"]


def test_swap_exchanges_axes():
    fig = Figure()
    draw(fig, page(swap=True, xlog=True, xlabel="Spannung"), {})
    ax, ax2 = fig.axes
    assert ax.get_ylabel() == "Spannung" and ax.get_xlabel() == "I / mA"
    assert ax.get_yscale() == "log" and ax2.get_xlabel() == "P / mW"  # twiny: 2. Achse oben
    line = ax.lines[0]
    np.testing.assert_array_equal(line.get_xdata(), [10, 20, 40])
    np.testing.assert_array_equal(line.get_ydata(), [1, 2, 4])


def test_style_override_per_series():
    fig = Figure()
    p = page()
    p.tables[0].columns[2].style = {"color": "#ff0000", "marker": "s"}
    draw(fig, p, {"marker": "^", "colors": "#00ff00"})
    ax, ax2 = fig.axes
    assert ax.lines[0].get_color() == "#ff0000" and ax.lines[0].get_marker() == "s"
    assert ax2.lines[0].get_color() == "#00ff00" and ax2.lines[0].get_marker() == "^"


def test_mathtext_validation():
    assert label_error(r"$\Delta U$ / mV") is None
    assert label_error(r"$\frac{a}{b") is not None
    assert safe("100 $ Preis") == r"100 \$ Preis"
    fig = Figure()
    draw(fig, page(title=r"$\frac{a}{b"), {})  # darf nicht werfen
    fig.canvas.draw()


@pytest.mark.parametrize("ext", ["png", "pdf", "svg"])
def test_export_size(tmp_path, ext):
    f = tmp_path / f"p.{ext}"
    export(page(), {}, str(f), 15.0, 10.0, 100)
    assert f.stat().st_size > 1000
    if ext == "png":
        w, h = (int.from_bytes(f.read_bytes()[i:i + 4], "big") for i in (16, 20))
        assert (w, h) == (590, 393)  # 15 cm × 10 cm bei 100 dpi, Matplotlib rundet ab


@pytest.mark.skipif(not (shutil.which("xelatex") or shutil.which("lualatex") or shutil.which("pdflatex")),
                    reason="PGF braucht LaTeX")
def test_export_pgf(tmp_path):
    f = tmp_path / "p.pgf"
    export(page(), {}, str(f), 12.0, 8.0, 100)
    assert "\\begin{pgfpicture}" in f.read_text(encoding="utf-8")
