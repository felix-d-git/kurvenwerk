"""Statistik einer Auswahl und Ergebnistexte (Statistik-Leiste, Fit-Güte) als Text bzw. siunitx."""
import numpy as np

from .rounding import fmt, parts


def describe(x, dx=None) -> dict:
    """Kennzahlen der endlichen Werte; gewichteter Mittelwert (w = 1/u_x²) nur, wenn alle u_x > 0."""
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


def param(n: str, v: float, e: float, free=True, rounded=True, tex=False, pct=False) -> str:
    """Fit-Parameter mit eigener Unsicherheit: `a = 1.20, u_a = 0.10` bzw. siunitx; fix → nur der Wert."""
    if not free:
        return rf"${n}$ = \num{{{fmt(v, None, rounded)}}} (fix)" if tex else f"{n} = {fmt(v, None, rounded)} (fix)"
    vs, es = parts(v, e, rounded, pct)
    if not tex:
        return f"{n} = {vs}, u_{n} = {es}"
    es = rf"\qty{{{es[:-2]}}}{{\percent}}" if es.endswith(" %") else rf"\num{{{es}}}"
    return rf"${n}$ = \num{{{vs}}}, $u_{{{n}}}$ = {es}"


def fit_short(r, rounded=True, pct=False) -> str:
    """Kurzergebnis fürs Panel: je Parameter eine Zeile, dazu χ²/ndf (gewichtet) bzw. R²."""
    lines = [param(n, v, e, fr, rounded, pct=pct) for n, v, e, fr in zip(r.params, r.values, r.errors, r.free)]
    if r.absolute and r.ndf:
        lines.append(f"χ²/ndf = {r.chi2 / r.ndf:.3g}")
    elif np.isfinite(r.r2):
        lines.append(f"R² = {r.r2:.4g}")
    return "\n".join(lines)


def fit_report(r, rounded=True, tex=False, pct=False) -> str:
    """Parameter mit u_<Parameter>, Güte und (nur Text) Kovarianz-/Korrelationsmatrix eines fit.Result."""
    lines = [param(n, v, e, fr, rounded, tex, pct) for n, v, e, fr in zip(r.params, r.values, r.errors, r.free)]
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


def _finite(x) -> np.ndarray:
    x = np.asarray(x, float)
    return x[np.isfinite(x)]


def ttest(x, mu0: float) -> dict:
    """Einstichproben-t-Test H₀: μ = μ₀ (zweiseitig)."""
    from scipy import stats as st
    d = describe(x)
    if d["n"] < 2 or not d["std"]:
        return {}
    t = (d["mean"] - mu0) / d["sem"]
    return {"t": t, "df": d["n"] - 1, "p": float(2 * st.t.sf(abs(t), d["n"] - 1)), "mean": d["mean"], "sem": d["sem"]}


def welch(x, y) -> dict:
    """Welch-t-Test zweier Stichproben: Differenz x̄₁ − x̄₂ ± √(s₁²/n₁ + s₂²/n₂), Freiheitsgrade nach Satterthwaite."""
    from scipy import stats as st
    a, b = describe(x), describe(y)
    if a["n"] < 2 or b["n"] < 2:
        return {}
    va, vb = a["sem"] ** 2, b["sem"] ** 2
    u = np.sqrt(va + vb)
    if not u:
        return {}
    df = (va + vb) ** 2 / (va ** 2 / (a["n"] - 1) + vb ** 2 / (b["n"] - 1))
    diff = a["mean"] - b["mean"]
    t = diff / u
    return {"diff": diff, "u": float(u), "t": t, "df": float(df), "p": float(2 * st.t.sf(abs(t), df))}


def outliers_iqr(x, k: float = 1.5) -> np.ndarray:
    """Maske: außerhalb [Q1 − k·IQR, Q3 + k·IQR] (Tukey)."""
    x = np.asarray(x, float)
    q1, q3 = np.nanpercentile(x, [25, 75]) if np.isfinite(x).any() else (np.nan, np.nan)
    return (x < q1 - k * (q3 - q1)) | (x > q3 + k * (q3 - q1))


def grubbs_crit(n: int, alpha: float = 0.05) -> float:
    """Kritischer Wert des zweiseitigen Grubbs-Tests."""
    from scipy import stats as st
    t = st.t.ppf(1 - alpha / (2 * n), n - 2)
    return (n - 1) / np.sqrt(n) * np.sqrt(t * t / (n - 2 + t * t))


def outliers_grubbs(x, alpha: float = 0.05) -> np.ndarray:
    """Maske: Grubbs-Test wiederholt, solange der extremste Wert signifikant ist (ab n = 3)."""
    x = np.asarray(x, float)
    out = np.zeros(len(x), bool)
    while (n := int((keep := np.isfinite(x) & ~out).sum())) >= 3:
        v = x[keep]
        s = v.std(ddof=1)
        if not s:
            break
        g = np.where(keep, np.abs(x - v.mean()), -1)
        i = int(np.argmax(g))
        if g[i] / s <= grubbs_crit(n, alpha):
            break
        out[i] = True
    return out


def _p(p: float) -> str:
    return "< 0.001" if p < 1e-3 else f"{p:.3g}"


def ttest_text(r: dict, mu0: float, alpha: float, tex=False) -> str:
    """t-Test-Ergebnis mit Entscheidung über H₀ bei α."""
    if not r:
        return ""
    keep = r["p"] >= alpha
    dec = f"H₀ (μ = {mu0:g}) {'beibehalten' if keep else 'verworfen'} bei α = {alpha:g}"
    if tex:
        p = r"p < \num{0.001}" if r["p"] < 1e-3 else rf"p = \num{{{r['p']:.3g}}}"
        return (rf"$t = \num{{{r['t']:.4g}}}$, $\nu = {r['df']}$, ${p}$" + "\n"
                + rf"$H_0$ ($\mu = \num{{{mu0:g}}}$) {'beibehalten' if keep else 'verworfen'} bei $\alpha = \num{{{alpha:g}}}$")
    return f"t = {r['t']:.4g}  ·  ν = {r['df']}  ·  p = {_p(r['p'])}\n{dec}"


def welch_text(r: dict, rounded=True, tex=False, unit="", pct=False) -> str:
    """Differenz ± Unsicherheit, t, ν, p."""
    if not r:
        return ""
    d = fmt(r["diff"], r["u"], rounded, tex, unit, pct)
    if tex:
        p = r"p < \num{0.001}" if r["p"] < 1e-3 else rf"p = \num{{{r['p']:.3g}}}"
        return (rf"$\Delta\bar{{x}}$ = {d}" + "\n"
                + rf"$t = \num{{{r['t']:.4g}}}$, $\nu = \num{{{r['df']:.3g}}}$, ${p}$")
    return f"Δx̄ = {d}\nt = {r['t']:.4g}  ·  ν = {r['df']:.3g}  ·  p = {_p(r['p'])}"
