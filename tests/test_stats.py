"""Statistik gegen NIST StRD (Univariate Summary Statistics, NumAcc1–4: zertifizierte Werte) und Handrechnung."""
import math

import numpy as np

from kurvenwerk import fit as fitting
from kurvenwerk.stats import describe, fit_report, fit_short, summary


def numacc(base: float, step: float) -> np.ndarray:
    """NumAcc2–4: base, dann 500 × (base − step, base + step); 1001 Werte."""
    return np.array([base] + [base - step, base + step] * 500)


def test_nist_numacc():
    d = describe([10000001, 10000003, 10000002])  # NumAcc1
    assert d["mean"] == 10000002 and math.isclose(d["std"], 1.0, rel_tol=1e-12)
    for base, tol in [(1.2, 1e-12), (1000000.2, 1e-8), (10000000.2, 1e-7)]:  # NumAcc2, 3, 4
        d = describe(numacc(base, 0.1))
        assert math.isclose(d["mean"], base, rel_tol=1e-14), base
        assert math.isclose(d["std"], 0.1, rel_tol=tol), (base, d["std"])
        assert d["n"] == 1001 and math.isclose(d["sem"], 0.1 / math.sqrt(1001), rel_tol=tol)


def test_describe_basic_and_weighted():
    d = describe([1, 3, 2, 5, 4, np.nan], dx=[1, 1, 2, 1, 1, 1])
    assert (d["n"], d["median"], d["min"], d["max"]) == (5, 3, 1, 5)
    assert math.isclose(d["std"], math.sqrt(2.5))
    # w = 1,1,1/4,1,1 → x̄w = (1+3+0.5+5+4)/4.25, Fehler 1/√4.25
    assert math.isclose(d["wmean"], 13.5 / 4.25) and math.isclose(d["wmean_err"], 1 / math.sqrt(4.25))
    assert "wmean" not in describe([1, 2], dx=[1, 0])
    assert describe([]) == {"n": 0} and summary({"n": 0}) == ""
    s = summary(describe([1, 2, 3]), unit="mV")
    assert "x̄ = (2.0 ± 0.6) mV" in s and "n = 3" in s
    assert r"$\bar{x}$ = \qty{2.0 \pm 0.6}{mV}" in summary(describe([1, 2, 3]), tex=True, unit="mV")


X, Y = np.arange(1.0, 6.0), np.array([1.0, 3, 2, 5, 4])  # Sxx = Syy = 10, Sxy = 8 → b = 0.8, R² = 0.64


def test_fit_goodness_unweighted():
    r = fitting.fit("a*x + b", X, Y)
    assert np.allclose(r.values, [0.8, 0.6])
    assert math.isclose(r.r2, 0.64) and math.isclose(r.r2adj, 1 - 0.36 * 4 / 3)
    assert math.isclose(r.rmse, math.sqrt(3.6 / 5))  # SS_res = Syy(1 − R²) = 3.6
    assert math.isclose(r.errors[0], math.sqrt(1.2 / 10))  # s² = 3.6/3
    assert math.isclose(r.corr[0, 1], -3 / math.sqrt(11))  # −x̄ / √(Σx²/n)
    assert math.isnan(r.p)
    t = fit_report(r)
    assert "a = 0.8 ± 0.4" in t and "R² = 0.64" in t and "Korrelation" in t


def test_fit_goodness_weighted_p():
    r = fitting.fit("a*x + b", X, Y, dy=np.ones(5))
    assert math.isclose(r.chi2, 3.6) and r.ndf == 3 and math.isclose(r.r2, 0.64)
    # P(χ²₃ > c) = erfc(√(c/2)) + √(2c/π)·e^(−c/2)
    c = 3.6
    assert math.isclose(r.p, math.erfc(math.sqrt(c / 2)) + math.sqrt(2 * c / math.pi) * math.exp(-c / 2))
    assert "χ²/ndf = 1.2" in fit_report(r) and r"$a$ = \num{0.8 \pm 0.4}" in fit_report(r, tex=True)


def test_fit_short():
    t = fit_short(fitting.fit("a*x + b", X, Y)).splitlines()
    assert t[0] == "a = 0.8 ± 0.4" and t[-1] == "R² = 0.64" and len(t) == 3
    assert fit_short(fitting.fit("a*x + b", X, Y, dy=np.ones(5))).endswith("χ²/ndf = 1.2")
