"""Plot ohne Qt: Reihen aus Tabellen holen, auf eine Matplotlib-Figure zeichnen, exportieren."""
from dataclasses import dataclass

import numpy as np
from matplotlib.figure import Figure
from matplotlib.mathtext import MathTextParser

from . import fit as fitting
from .formula import error_column
from .model import Column, Page, Table

CM = 1 / 2.54
EXPORT_FORMATS = ("png", "pdf", "svg", "pgf")
MARKERS = ("o", "s", "^", "v", "D", "x", "+", ".", "none")
LINESTYLES = ("none", "-", "--", ":", "-.")
# Projektweiter Stil (Project.style); fehlende Schlüssel → diese Defaults
STYLE = {"marker": "o", "markersize": 5.0, "linestyle": "none", "linewidth": 1.2, "capsize": 3.0,
         "fontsize": 10.0, "font": "serif", "grid": True,
         "colors": "#1f77b4, #d62728, #2ca02c, #ff7f0e, #9467bd, #8c564b",
         "export_w": 15.0, "export_h": 10.0, "export_dpi": 300}
# Achsen/Beschriftung pro Seite (Page.plot); None bei Grenzen = automatisch
PLOT = {"title": "", "xlabel": "", "ylabel": "", "y2label": "", "xlog": False, "ylog": False,
        "y2log": False, "xmin": None, "xmax": None, "ymin": None, "ymax": None, "y2min": None,
        "y2max": None, "legend": True, "swap": False, "residuals": False}
# Überschreiben pro Reihe (Column.style); "" = Projektstil
SERIES = {"label": "", "color": "", "marker": "", "linestyle": "", "axis": "y"}

_mathtext = MathTextParser("path")


@dataclass
class Series:
    x: np.ndarray
    y: np.ndarray
    dx: np.ndarray | None
    dy: np.ndarray | None
    xcol: Column
    ycol: Column
    rows: np.ndarray  # Tabellenzeile je Punkt (für Fit-Ausschluss)


def label_error(text: str) -> str | None:
    """Mathtext-Fehler (z.B. `$\\frac{a}{b`) als Text, sonst None."""
    try:
        _mathtext.parse(text)
    except ValueError as e:
        return (str(e).strip().splitlines() or ["ungültige Formel"])[-1]
    return None


def safe(text: str) -> str:
    """Ungültige Mathe als Klartext zeigen statt beim Zeichnen abzustürzen."""
    return text.replace("$", r"\$") if label_error(text) else text


def heading(c: Column) -> str:
    return f"{c.name} / {c.unit}" if c.unit else c.name


def _arr(vals: list, n: int) -> np.ndarray:
    a = np.full(n, np.nan)
    v = np.array([np.nan if x is None else x for x in vals[:n]], float)
    a[:len(v)] = v
    return a


def _error(cols: list[Column], j: int) -> Column | None:
    """Δ<Name>, sonst eine Δ-Spalte direkt rechts daneben."""
    c = cols[j]
    e = error_column(cols, c.name)
    want = "Δx" if c.role == "X" else "Δy"
    if e is None and j + 1 < len(cols) and cols[j + 1].role == want:
        e = cols[j + 1]
    return e


def series(table: Table) -> list[Series]:
    """Je Y-Spalte eine Reihe gegen die erste X-Spalte; Zeilen ohne x oder y fallen weg."""
    cols = table.columns
    xi = next((i for i, c in enumerate(cols) if c.role == "X"), None)
    if xi is None:
        return []
    xc, out = cols[xi], []
    dxc = _error(cols, xi)
    for j, yc in enumerate(cols):
        if yc.role != "Y":
            continue
        n = max(len(xc.values), len(yc.values))
        x, y = _arr(xc.values, n), _arr(yc.values, n)
        ok = ~(np.isnan(x) | np.isnan(y))
        if not ok.any():
            continue
        dyc = _error(cols, j)
        dx = np.abs(np.nan_to_num(_arr(dxc.values, n)[ok])) if dxc else None  # errorbar verbietet Δ < 0
        dy = np.abs(np.nan_to_num(_arr(dyc.values, n)[ok])) if dyc else None
        out.append(Series(x[ok], y[ok], dx, dy, xc, yc, np.flatnonzero(ok)))
    return out


def fit_mask(s: Series) -> np.ndarray:
    """Punkte im Fit-Bereich und nicht ausgeschlossen."""
    f = {**fitting.FIT, **s.ycol.fit}
    m = ~np.isin(s.rows, f["excluded"])
    if f["xmin"] is not None:
        m &= s.x >= f["xmin"]
    if f["xmax"] is not None:
        m &= s.x <= f["xmax"]
    return m


def run_fit(s: Series) -> tuple[fitting.Result, np.ndarray]:
    """Fit der Reihe nach Column.fit → (Ergebnis, benutzte Punkte). Wirft FitError/FormulaError."""
    m = fit_mask(s)
    cut = lambda a: None if a is None else a[m]  # noqa: E731
    return fitting.fit(s.ycol.fit.get("formula", ""), s.x[m], s.y[m], cut(s.dx), cut(s.dy), s.ycol.fit.get("params")), m


def _auto(names: list[str]) -> str:
    return ", ".join(dict.fromkeys(n for n in names if n))


def draw(fig: Figure, page: Page, style: dict) -> list[tuple]:
    """Figure komplett neu aufbauen. swap tauscht Daten, Fehler, Beschriftung, Log und Grenzen von x und y.
    → [(Achse, Reihe, gezeichnete x, gezeichnete y)] fürs Anklicken von Punkten."""
    st, pl = {**STYLE, **style}, {**PLOT, **page.plot}
    fig.clear()
    fig.set_facecolor("white")
    rc = {"size": st["fontsize"], "family": st["font"]}
    colors = [c.strip() for c in str(st["colors"]).split(",") if c.strip()] or ["C0"]
    all_s = [s for t in page.tables for s in series(t)]
    fits = {}
    for s in all_s:
        if s.ycol.fit.get("formula"):
            try:
                fits[id(s)] = run_fit(s)
            except ValueError as e:  # FitError, FormulaError
                fits[id(s)] = str(e)
    swap = pl["swap"]
    # ponytail: Residuenplot nur ohne Achsentausch (dann müsste er rechts daneben stehen)
    if pl["residuals"] and not swap and any(not isinstance(r, str) for r in fits.values()):
        gs = fig.add_gridspec(2, 1, height_ratios=(3, 1))
        ax = fig.add_subplot(gs[0])
        rax = fig.add_subplot(gs[1], sharex=ax)
        ax.tick_params(labelbottom=False)
        rax.axhline(0, color="0.4", linewidth=st["linewidth"] * 0.8)
        rax.set_ylabel("Residuen", fontdict=rc)
        rax.grid(bool(st["grid"]), alpha=0.3)
    else:
        ax, rax = fig.add_subplot(), None
    ax.grid(bool(st["grid"]), alpha=0.3)
    has2 = any({**SERIES, **s.ycol.style}["axis"] == "y2" for s in all_s)
    ax2 = (ax.twiny() if pl["swap"] else ax.twinx()) if has2 else None
    names = {"x": [], "y": [], "y2": []}
    drawn, errors = [], []
    for i, s in enumerate(all_s):
        o = {**SERIES, **s.ycol.style}
        a = ax2 if o["axis"] == "y2" and ax2 else ax
        x, y, dx, dy = (s.y, s.x, s.dy, s.dx) if swap else (s.x, s.y, s.dx, s.dy)
        ls = o["linestyle"] or st["linestyle"]
        color = o["color"] or colors[i % len(colors)]
        out = np.isin(s.rows, s.ycol.fit.get("excluded", []))  # ausgeschlossen → hohl, ohne Balken
        cut = lambda v: None if v is None else v[~out]  # noqa: E731
        a.errorbar(x[~out], y[~out], xerr=cut(dx), yerr=cut(dy), label=safe(o["label"] or heading(s.ycol)),
                   color=color, marker=o["marker"] or st["marker"],
                   markersize=st["markersize"], linestyle="none" if ls == "none" else ls,
                   linewidth=st["linewidth"], capsize=st["capsize"], elinewidth=st["linewidth"] * 0.8)
        if out.any():
            a.plot(x[out], y[out], linestyle="none", marker=o["marker"] or st["marker"], markersize=st["markersize"],
                   markerfacecolor="none", markeredgecolor=color, alpha=0.6)
        drawn.append((a, s, x, y))
        r = fits.get(id(s))
        if isinstance(r, str):
            errors.append(f"Fit {s.ycol.name}: {r}")
        elif r:
            _draw_fit(a, rax, s, *r, color, st, pl, swap)
        names["x"].append(heading(s.xcol))
        names["y2" if a is ax2 else "y"].append(heading(s.ycol))

    # Beschriftung/Log/Grenzen in Daten-Koordinaten x/y; bei swap landen sie auf der anderen Achse
    xlab = pl["xlabel"] or _auto(names["x"])
    ylab = pl["ylabel"] or _auto(names["y"])
    y2lab = pl["y2label"] or _auto(names["y2"])
    hx, vy = ("y", "x") if swap else ("x", "y")
    for a, axis, lab, log, lo, hi in [(ax, hx, xlab, pl["xlog"], pl["xmin"], pl["xmax"]),
                                     (ax, vy, ylab, pl["ylog"], pl["ymin"], pl["ymax"]),
                                     (ax2, vy, y2lab, pl["y2log"], pl["y2min"], pl["y2max"])]:
        if a is None:
            continue
        getattr(a, f"set_{axis}label")(safe(lab), fontdict=rc)
        if log:
            getattr(a, f"set_{axis}scale")("log")
        if lo is not None or hi is not None:
            getattr(a, f"set_{axis}lim")(lo, hi)
        a.tick_params(labelsize=st["fontsize"] * 0.9)
    if rax is not None:  # x-Beschriftung wandert unter den Residuenplot
        rax.set_xlabel(ax.get_xlabel(), fontdict=rc)
        ax.set_xlabel("")
        rax.tick_params(labelsize=st["fontsize"] * 0.9)
    if pl["title"]:
        ax.set_title(safe(pl["title"]), fontdict=rc)
    if pl["legend"] and all_s:
        handles = [h for a in (ax, ax2) if a for h in a.get_legend_handles_labels()[0]]
        ax.legend(handles=handles, prop=rc)
    if errors:
        ax.text(0.01, 0.99, "\n".join(errors), transform=ax.transAxes, va="top", color="#d62728",
                fontsize=st["fontsize"] * 0.8, wrap=True)
    return drawn


def _draw_fit(a, rax, s: Series, r: fitting.Result, m: np.ndarray, color, st: dict, pl: dict, swap: bool):
    """Fitkurve über den Fit-Bereich, optional Band, Residuen der benutzten Punkte."""
    f = {**fitting.FIT, **s.ycol.fit}
    lo, hi = s.x[m].min(), s.x[m].max()
    xs = np.geomspace(lo, hi, 400) if pl["xlog"] and lo > 0 else np.linspace(lo, hi, 400)
    ys = r(xs)
    pts = (ys, xs) if swap else (xs, ys)
    a.plot(*pts, color=color, linewidth=st["linewidth"] * 1.2, label=f"Fit {s.ycol.name}")
    if f["band"] in ("conf", "pred"):
        h = r.band(xs, f["band"], f["level"])
        (a.fill_betweenx if swap else a.fill_between)(xs, ys - h, ys + h, color=color, alpha=0.15, linewidth=0)
    if rax is not None:
        rax.errorbar(s.x[m], s.y[m] - r(s.x[m]), yerr=None if s.dy is None else s.dy[m], color=color,
                     marker=st["marker"], markersize=st["markersize"] * 0.8, linestyle="none",
                     capsize=st["capsize"], elinewidth=st["linewidth"] * 0.8)


def export(page: Page, style: dict, path: str, w_cm: float, h_cm: float, dpi: int) -> None:
    """Eigene Figure in Zielgröße → Bildschirm-Canvas bleibt unberührt. PGF braucht LaTeX (lualatex/xelatex/pdflatex)."""
    fig = Figure(figsize=(w_cm * CM, h_cm * CM), dpi=dpi, layout="constrained")
    draw(fig, page, style)
    if path.lower().endswith(".pgf"):
        from matplotlib.backends.backend_pgf import FigureCanvasPgf
        FigureCanvasPgf(fig)
    fig.savefig(path, dpi=dpi)
