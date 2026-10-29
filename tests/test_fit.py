"""Fit gegen synthetische Daten mit bekannten Parametern und gegen geschlossene Lehrbuchformeln
(lineare Regression: Parameterfehler, Konfidenz-/Prognoseband)."""
import numpy as np
import pytest
import sympy as sp
from scipy import stats

from kurvenwerk.fit import TEMPLATES, FitError, fit, model, polynomial
from kurvenwerk.formula import FormulaError

X = np.linspace(0.5, 10, 12)
NOISE = np.array([.3, -.2, .1, .4, -.5, .2, -.1, -.3, .5, -.2, .1, -.3])  # fest, synthetisch


def test_model_params_and_rejects():
    assert model("A*exp(-(x - mu)^2/(2*sigma^2)) + c")[1] == ["A", "mu", "sigma", "c"]
    assert model("a*e^x + pi")[1] == ["a"]  # e, pi sind Konstanten
    assert model(r"\frac{A}{x - x_0}")[1] == ["A", "x_0"]
    assert polynomial(0) == "a0" and polynomial(3) == "a0 + a1*x + a2*x^2 + a3*x^3"
    with pytest.raises(FitError):
        model("2*x")
    with pytest.raises(FormulaError):
        model("__import__('os')")


def test_linear_unweighted_matches_textbook():
    y = 2 * X + 1 + NOISE
    r = fit("a*x + b", X, y)
    n, xm = len(X), X.mean()
    sxx = ((X - xm) ** 2).sum()
    a = ((X - xm) * (y - y.mean())).sum() / sxx
    b = y.mean() - a * xm
    s = np.sqrt(((y - a * X - b) ** 2).sum() / (n - 2))
    np.testing.assert_allclose(r.values, [a, b], rtol=1e-9)
    np.testing.assert_allclose(r.errors, [s / np.sqrt(sxx), s * np.sqrt(1 / n + xm ** 2 / sxx)], rtol=1e-6)
    assert r.ndf == n - 2 and r.method == "ungewichtet"
    x0 = np.array([0.0, 5.0, 12.0])
    t = stats.t.ppf(0.975, n - 2)
    np.testing.assert_allclose(r.band(x0), t * s * np.sqrt(1 / n + (x0 - xm) ** 2 / sxx), rtol=1e-6)
    np.testing.assert_allclose(r.band(x0, "pred"), t * s * np.sqrt(1 + 1 / n + (x0 - xm) ** 2 / sxx), rtol=1e-6)


def test_weighted_absolute_errors():
    dy = np.linspace(0.1, 0.6, len(X))
    y = 2 * X + 1 + NOISE * dy
    r = fit("a*x + b", X, y, dy=dy)
    w = 1 / dy ** 2  # gewichtete Regression geschlossen
    S, Sx, Sy, Sxx, Sxy = w.sum(), (w * X).sum(), (w * y).sum(), (w * X * X).sum(), (w * X * y).sum()
    D = S * Sxx - Sx ** 2
    np.testing.assert_allclose(r.values, [(S * Sxy - Sx * Sy) / D, (Sxx * Sy - Sx * Sxy) / D], rtol=1e-8)
    np.testing.assert_allclose(r.errors, [np.sqrt(S / D), np.sqrt(Sxx / D)], rtol=1e-6)
    assert r.chi2 == pytest.approx((w * (y - r(X)) ** 2).sum()) and r.absolute
    np.testing.assert_allclose(r.band([3.0]), 1.959964 * np.sqrt((Sxx - 2 * 3 * Sx + 9 * S) / D), rtol=1e-5)


def test_effective_variance_with_dx():
    """Gerade, konstante Δx/Δy → σ_eff² = Δy² + a²Δx² für alle Punkte: Werte wie OLS, Fehler σ_eff/√Sxx."""
    y = 2 * X + 1 + NOISE
    dx, dy = np.full(len(X), 0.2), np.full(len(X), 0.3)
    r = fit("a*x + b", X, y, dx=dx, dy=dy)
    ols = fit("a*x + b", X, y)
    np.testing.assert_allclose(r.values, ols.values, rtol=1e-9)
    s_eff = np.sqrt(0.3 ** 2 + (r.values[0] * 0.2) ** 2)
    np.testing.assert_allclose(r.errors[0], s_eff / np.sqrt(((X - X.mean()) ** 2).sum()), rtol=1e-6)
    assert r.method.startswith("effektive Varianz")
    assert fit("a*x + b", X, y, dx=np.r_[0.0, dx[1:]], dy=dy).method == "gewichtet (u_y)"  # Δx lückenhaft


def test_fixed_and_bounds():
    y = 2 * X + 1
    r = fit("a*x + b", X, y, spec={"b": {"value": 0, "fixed": True}})
    assert r.values[1] == 0 and r.errors[1] == 0
    assert r.values[0] == pytest.approx((X * y).sum() / (X * X).sum())
    r = fit("a*x + b", X, y, spec={"a": {"value": 1, "max": 1.5}})
    assert r.values[0] == pytest.approx(1.5)
    with pytest.raises(FitError, match="Grenzen"):
        fit("a*x + b", X, y, spec={"a": {"value": 3, "max": 1.5}})
    with pytest.raises(FitError, match="fixiert"):
        fit("a*x", X, y, spec={"a": {"fixed": True}})
    with pytest.raises(FitError, match="Startwerten"):
        fit("a*ln(x - 5)", X, y)


@pytest.mark.parametrize("name, true, start", [
    ("Exponentiell", [3, -0.4, 1], [2, -0.3, 0]),
    ("Logarithmisch", [2, 0.5], None),
    ("Potenz", [1.5, 0.7], [1, 1]),
    ("Gauß", [4, 5, 1.2, 0.5], [3, 4.5, 1, 0]),
    ("Lorentz", [4, 0.8, 5, 0.5], [3, 1, 4.5, 0]),
    ("Sinus", [2, 1.1, 0.3, 0.5], [2, 1.05, 0.2, 0]),
    ("Gedämpfte Schwingung", [3, 0.2, 2.0, 0.4, 0.1], [2.5, 0.15, 2.05, 0.3, 0]),
])
def test_templates_recover_parameters(name, true, start):
    x = np.linspace(0.5, 10, 60)
    expr, names = model(TEMPLATES[name])
    y = sp.lambdify([sp.Symbol("x")] + [sp.Symbol(n) for n in names], expr)(x, *true) * np.ones_like(x)
    spec = {n: {"value": v} for n, v in zip(names, start or [1] * len(names))}
    np.testing.assert_allclose(fit(TEMPLATES[name], x, y, spec=spec).values, true, rtol=1e-6, atol=1e-8)


def test_polynomial_noise_free():
    x = np.linspace(-2, 3, 20)
    np.testing.assert_allclose(fit(polynomial(3), x, 1 - 2 * x + 0.5 * x ** 3).values, [1, -2, 0, 0.5], atol=1e-9)


def test_nist_misra1a_certified():
    """NIST StRD Misra1a (nichtlinear, Schwierigkeit niedrig), Start 1: zertifizierte Werte + Fehler."""
    x = np.array([77.6, 114.9, 141.1, 190.8, 239.9, 289.0, 332.8, 378.4, 434.8, 477.3, 536.8, 593.1, 689.1, 760.0])
    y = np.array([10.07, 14.73, 17.94, 23.93, 29.61, 35.18, 40.02, 44.82, 50.76, 55.05, 61.01, 66.40, 75.47, 81.78])
    r = fit("b1*(1 - exp(-b2*x))", x, y, spec={"b1": {"value": 500}, "b2": {"value": 1e-4}})
    np.testing.assert_allclose(r.values, [2.3894212918e02, 5.5015643181e-04], rtol=1e-6)
    np.testing.assert_allclose(r.errors, [2.7070075241e00, 7.2668688436e-06], rtol=1e-4)


def test_bad_formulas_raise_fit_error():
    for t in ("", "2*x", "a*x + 1/0"):
        with pytest.raises(FitError):
            fit(t, X, X)
