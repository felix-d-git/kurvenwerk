"""Fit ohne Qt: Formel y(x) mit Parametern → scipy curve_fit. Δy wirkt als Gewicht (absolute Fehler),
Δx über die effektive Varianz σ² = Δy² + (∂f/∂x · Δx)², iteriert bis die Parameter stehen.
Kein scipy.odr: ab SciPy 1.17 abgekündigt, 1.19 entfernt; effektive Varianz kann zudem Grenzen/Fixieren."""
import re
from dataclasses import dataclass

import numpy as np
import sympy as sp
from scipy import optimize, stats

from .formula import CONSTS, FUNCS, parse

X = "x"
TEMPLATES = {
    "Linear": "a*x + b",
    "Exponentiell": "A*exp(b*x) + c",
    "Logarithmisch": "a*ln(x) + b",
    "Potenz": "a*x^b",
    "Gauß": "A*exp(-(x - mu)^2/(2*sigma^2)) + c",
    "Lorentz": "A*w^2/((x - x0)^2 + w^2) + c",
    "Sinus": "A*sin(omega*x + phi) + c",
    "Gedämpfte Schwingung": "A*exp(-delta*x)*sin(omega*x + phi) + c",
}
BANDS = {"": "keins", "conf": "Konfidenzband", "pred": "Prognoseband"}
# Fit einer Y-Spalte (Column.fit); params: {Name: {"value", "min", "max", "fixed"}}, excluded: Zeilen
FIT = {"formula": "", "params": {}, "xmin": None, "xmax": None, "excluded": [], "band": "", "level": 0.95}


class FitError(ValueError):
    pass


def polynomial(n: int) -> str:
    return " + ".join(["a0", "a1*x"][:n + 1] + [f"a{k}*x^{k}" for k in range(2, n + 1)])


def model(text: str) -> tuple[sp.Expr, list[str]]:
    """Formel → (Ausdruck, Parameter in Reihenfolge des Auftretens). Jeder Name außer x, Funktionen
    und Konstanten (pi, e) ist ein Parameter."""
    if not text.strip():
        raise FitError("Keine Formel")
    names = [n for n in dict.fromkeys(re.findall(r"[^\W\d]\w*", text)) if n not in FUNCS and n not in CONSTS]
    expr = parse(text, names)
    free = {s.name for s in expr.free_symbols} - {X}
    params = [n for n in names if n in free]
    params += sorted(free - set(params))  # LaTeX-Namen wie x_{0}
    if not params:
        raise FitError("Formel hat keine Parameter")
    return expr, params


def _eval(f, x, p) -> np.ndarray:
    with np.errstate(all="ignore"):
        return np.broadcast_to(np.asarray(f(x, *p), dtype=float), np.shape(x))


@dataclass
class Result:
    params: list[str]
    values: np.ndarray  # alle Parameter, fixierte mit ihrem Startwert
    errors: np.ndarray  # fixierte → 0
    free: np.ndarray  # bool je Parameter
    cov: np.ndarray  # nur freie Parameter
    chi2: float
    ndf: int
    absolute: bool  # Gewichte aus Δx/Δy → Fehler absolut, Band mit Normalquantil
    s2: float  # Streuung eines neuen Punktes fürs Prognoseband
    method: str
    _f: object
    _jac: list
    # Güte; R² mit denselben Gewichten wie χ², RMSE der ungewichteten Residuen, p nur bei Gewichten (χ²-Test)
    r2: float = np.nan
    r2adj: float = np.nan
    rmse: float = np.nan
    p: float = np.nan

    @property
    def corr(self) -> np.ndarray:
        d = np.sqrt(np.diag(self.cov))
        with np.errstate(all="ignore"):
            return self.cov / np.outer(d, d)

    def __call__(self, x) -> np.ndarray:
        return _eval(self._f, x, self.values)

    def band(self, x, kind: str = "conf", level: float = 0.95) -> np.ndarray:
        """Halbe Breite des Konfidenz- (conf) bzw. Prognosebands (pred), Delta-Methode."""
        x = np.asarray(x, float)
        J = np.column_stack([_eval(j, x, self.values) for j, fr in zip(self._jac, self.free) if fr])
        var = np.einsum("ij,jk,ik->i", J, self.cov, J)
        if kind == "pred":
            var = var + self.s2
        q = (1 + level) / 2
        k = stats.norm.ppf(q) if self.absolute else stats.t.ppf(q, self.ndf) if self.ndf > 0 else np.nan
        return k * np.sqrt(var)


def fit(text: str, x, y, dx=None, dy=None, spec: dict | None = None) -> Result:
    """spec = Column.fit["params"]. Δy/Δx zählen nur, wenn alle Werte > 0 (fehlend = 0 → ungewichtet)."""
    expr, names = model(text)
    spec = spec or {}
    get = lambda n, k, d: d if (v := spec.get(n, {}).get(k)) is None else v  # noqa: E731
    p0 = np.array([float(get(n, "value", 1.0)) for n in names])
    free = ~np.array([bool(get(n, "fixed", False)) for n in names])
    lo = np.array([float(get(n, "min", -np.inf)) for n in names])[free]
    hi = np.array([float(get(n, "max", np.inf)) for n in names])[free]
    x, y = np.asarray(x, float), np.asarray(y, float)
    nfree = int(free.sum())
    if not nfree:
        raise FitError("Alle Parameter fixiert")
    if len(x) < nfree:
        raise FitError(f"Zu wenige Punkte: {len(x)} für {nfree} freie Parameter")
    if np.any(lo > hi) or np.any(p0[free] < lo) or np.any(p0[free] > hi):
        raise FitError("Startwert außerhalb der Grenzen")
    syms = [sp.Symbol(X)] + [sp.Symbol(n) for n in names]
    try:  # z.B. 1/0 → zoo: lambdify kennt keine komplexe Unendlichkeit
        f = sp.lambdify(syms, expr, "numpy")
        jac = [sp.lambdify(syms, sp.diff(expr, s), "numpy") for s in syms[1:]]
        fx = sp.lambdify(syms, sp.diff(expr, syms[0]), "numpy")
    except Exception as e:  # noqa: BLE001 — sympy wirft beliebige Typen
        raise FitError(f"Formel nicht auswertbar: {e}") from None
    wy = dy is not None and len(dy) and np.all(np.asarray(dy) > 0)
    wx = dx is not None and len(dx) and np.all(np.asarray(dx) > 0)

    def full(pf):
        p = p0.copy()
        p[free] = pf
        return p

    def g(xx, *pf):
        return _eval(f, xx, full(pf))

    def dg(xx, *pf):  # analytische Jacobi-Matrix → genauer als Differenzenquotient
        p = full(pf)
        return np.column_stack([_eval(j, xx, p) for j, fr in zip(jac, free) if fr])

    if not np.all(np.isfinite(g(x, *p0[free]))):
        raise FitError("Modell bei den Startwerten nicht berechenbar (z.B. ln(x ≤ 0)) — Startwerte/Bereich prüfen")
    p, sigma = p0[free], None
    for _ in range(50 if wx else 1):
        if wx or wy:
            var = (np.asarray(dy, float) ** 2 if wy else 0) + \
                ((_eval(fx, x, full(p)) * np.asarray(dx, float)) ** 2 if wx else 0)
            if not np.all(var > 0):
                raise FitError("Δx ohne Δy braucht überall eine Steigung ≠ 0")
            sigma = np.sqrt(var)
        try:
            popt, pcov = optimize.curve_fit(g, x, y, p0=p, sigma=sigma, absolute_sigma=sigma is not None,
                                            jac=dg, bounds=(lo, hi), maxfev=20000)
        except (RuntimeError, ValueError) as e:
            raise FitError(f"Fit konvergiert nicht: {e}") from None
        done = np.allclose(popt, p, rtol=1e-10, atol=1e-14)
        p = popt
        if done:
            break
    r = y - g(x, *p)
    w = r / sigma if sigma is not None else r
    ndf = len(x) - nfree
    errors = np.zeros(len(names))
    errors[free] = np.sqrt(np.abs(np.diag(pcov)))
    # ponytail: Prognoseband gewichtet mit mittlerer Messvarianz, punktweises σ(x) erst wenn gefragt
    s2 = float(np.mean(sigma ** 2)) if sigma is not None else float(r @ r / ndf) if ndf else np.nan
    wt = 1 / sigma ** 2 if sigma is not None else np.ones_like(y)
    sst = float(wt @ (y - wt @ y / wt.sum()) ** 2)
    chi2 = float(w @ w)
    r2 = 1 - chi2 / sst if sst > 0 else np.nan
    q = dict(r2=r2, r2adj=1 - (1 - r2) * (len(x) - 1) / ndf if ndf else np.nan, rmse=float(np.sqrt(np.mean(r ** 2))),
             p=float(stats.chi2.sf(chi2, ndf)) if sigma is not None and ndf else np.nan)
    method = "effektive Varianz (Δx, Δy)" if wx else "gewichtet (Δy)" if wy else "ungewichtet"
    return Result(names, full(p), errors, free, pcov, chi2, ndf, sigma is not None, s2, method, f, jac, **q)

