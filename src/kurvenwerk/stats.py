"""Statistik einer Auswahl und Ergebnistexte (Statistik-Leiste, Fit-Güte) als Text bzw. siunitx."""
import numpy as np

from .rounding import fmt


def describe(x, dx=None) -> dict:
    """Kennzahlen der endlichen Werte; gewichteter Mittelwert (w = 1/Δx²) nur, wenn alle Δx > 0."""
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    x = x[ok]
    n = len(x)
    if not n:
        return {"n": 0}
    std = float(x.std(ddof=1)) if n > 1 else np.nan
    d = {"n": n, "mean": float(x.mean()), "std": std, "sem": std / np.sqrt(n), "median": float(np.median(x)),
         "min": float(x.min()), "max": float(x.max())}
    if dx is not None:
        dx = np.asarray(dx, float)[ok]
        if np.all(dx > 0):
            w = 1 / dx ** 2
            d["wmean"], d["wmean_err"] = float(w @ x / w.sum()), float(1 / np.sqrt(w.sum()))
    return d


def summary(d: dict, rounded=True, tex=False, unit="", pct=False) -> str:
    """Statistik-Leiste: eine Zeile Text bzw. eine siunitx-Zeile je Kennzahl."""
    if not d.get("n"):
        return ""
    rows = [("n", "n", d["n"], None, ""), ("x̄", r"\bar{x}", d["mean"], d["sem"], unit),
            ("s", "s", d["std"], None, unit), ("SEM", r"\mathrm{SEM}", d["sem"], None, unit),
            ("Median", r"\tilde{x}", d["median"], None, unit), ("Min", r"x_\mathrm{min}", d["min"], None, unit),
            ("Max", r"x_\mathrm{max}", d["max"], None, unit)]
    if "wmean" in d:
        rows.append(("x̄w", r"\bar{x}_w", d["wmean"], d["wmean_err"], unit))
    if tex:
        return "\n".join(f"${lx}$ = {fmt(v, e, rounded, True, u, pct)}" for _, lx, v, e, u in rows if np.isfinite(v))
    return "  ·  ".join(f"{lt} = {fmt(v, e, rounded, False, u, pct)}" for lt, _, v, e, u in rows if np.isfinite(v))


def fit_report(r, rounded=True, tex=False, pct=False) -> str:
    """Parameter ± Fehler, Güte und (nur Text) Kovarianz-/Korrelationsmatrix eines fit.Result."""
    lines = []
    for n, v, e, fr in zip(r.params, r.values, r.errors, r.free):
        val = fmt(v, e if fr else None, rounded, tex, pct=pct)
        lines.append(f"${n}$ = {val}" if tex else f"{n} = {val}" + ("" if fr else " (fix)"))
    g = [("R²", "R^2", r.r2), ("adj. R²", r"\bar{R}^2", r.r2adj), ("RMSE", r"\mathrm{RMSE}", r.rmse)]
    if r.absolute:
        g += [("χ²/ndf", r"\chi^2/\mathrm{ndf}", r.chi2 / r.ndf if r.ndf else np.nan), ("p", "p", r.p)]
    for lt, lx, v in g:
        if np.isfinite(v):
            lines.append(f"${lx}$ = \\num{{{v:.4g}}}" if tex else f"{lt} = {v:.4g}")
    if tex:
        return "\n".join(lines)
    lines.append(f"χ² = {r.chi2:.4g}, ndf = {r.ndf}" if r.absolute else f"Residuen² = {r.chi2:.4g}, ndf = {r.ndf}")
    lines.append(f"Methode: {r.method}")
    names = [n for n, fr in zip(r.params, r.free) if fr]
    if len(names) > 1:
        w = max(len(n) for n in names)
        for title, m, f in [("Kovarianz", r.cov, "{:>11.3e}"), ("Korrelation", r.corr, "{:>7.3f}")]:
            lines.append(f"{title}:")
            lines += [f"  {n:<{w}} " + " ".join(f.format(c) for c in row) for n, row in zip(names, m)]
    return "\n".join(lines)
