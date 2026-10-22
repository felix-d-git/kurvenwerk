"""Formel-Parser, Spaltenformeln, Gauß-Fehlerfortpflanzung und SI-Präfixe gegen Handrechnung."""
import math

import numpy as np
import pytest
import sympy as sp

from kurvenwerk.formula import FormulaError, number, parse, prefix_factor, recompute, row_value
from kurvenwerk.model import Column

U, I, t = sp.symbols("U I t")


@pytest.mark.parametrize("text, expected", [
    ("U*I", U * I),
    ("2U^2", 2 * U ** 2),  # implizite Multiplikation, ^ als Potenz
    ("U**2/I", U ** 2 / I),
    ("sqrt(U) + ln(I)", sp.sqrt(U) + sp.log(I)),
    ("exp(-t/2)", sp.exp(-t / 2)),
    (r"\frac{U}{I}", U / I),
    (r"$U \cdot e^{-t}$", U * sp.exp(-t)),  # Markdown, e = Eulersche Zahl
    (r"\sqrt{U^2+I^2}", sp.sqrt(U ** 2 + I ** 2)),
    (r"\pi U", sp.pi * U),
])
def test_parse(text, expected):
    assert sp.simplify(parse(text, ["U", "I", "t"]) - expected) == 0


def test_latex_index_names():
    assert parse(r"U_{0} \cdot 2", ["U_0"]) == 2 * sp.Symbol("U_0")


@pytest.mark.parametrize("text", [
    "__import__('os')", "U.__class__", "().__class__", "open('x')", "[1]", "lambda: 1",
    "x+1", "U = 1", r"\frac{x}{2}", "",
])
def test_rejects(text):
    with pytest.raises(FormulaError):
        parse(text, ["U"])


def test_number():
    assert number("1e-3") == 1e-3
    assert number("1/4") == 0.25
    assert number("2pi") == pytest.approx(2 * math.pi)
    with pytest.raises(FormulaError):
        number("sqrt(-1)")


def table():
    return [Column("U", "V", "X", [2.0, 4.0, None]), Column("ΔU", "V", "Δx", [0.1, 0.1, 0.1]),
            Column("I", "A", "Y", [3.0, 5.0, 1.0]), Column("ΔI", "A", "Δy", [0.2, 0.2, 0.2])]


def test_gauss_product():
    # P = U·I, ΔP = √((I·ΔU)² + (U·ΔI)²): Zeile 1 √(0,09+0,16) = 0,5; Zeile 2 √(0,25+0,64)
    cols = table() + [Column("P", "W", "Y", formula="U*I", gauss=True)]
    assert recompute(cols) == {}
    p, dp = cols[4], cols[5]
    assert p.values == [6.0, 20.0, None]
    assert (dp.name, dp.unit, dp.role) == ("ΔP", "W", "Δy")
    assert dp.values[:2] == pytest.approx([0.5, math.sqrt(0.89)]) and dp.values[2] is None


def test_gauss_quotient_and_chain():
    # R = U/I: ΔR/R = √((ΔU/U)² + (ΔI/I)²) → Zeile 1: R = 2/3, ΔR = 1/18
    # S = 3R hängt von R ab (steht links davon) und erbt ΔS = 3ΔR
    cols = table() + [Column("S", "", "Y", formula="3R", gauss=True),
                      Column("R", "Ω", "Y", formula=r"\frac{U}{I}", gauss=True)]
    assert recompute(cols) == {}
    by = {c.name: c for c in cols}
    assert by["R"].values[0] == pytest.approx(2 / 3)
    assert by["ΔR"].values[0] == pytest.approx(1 / 18)
    assert by["S"].values[0] == pytest.approx(2) and by["ΔS"].values[0] == pytest.approx(3 / 18)


def test_gauss_nonlinear():
    # f = ln(U) → Δf = ΔU/U = 0,05; g = U²·sin(I) → Δg = √((2U·sin I·ΔU)² + (U²·cos I·ΔI)²)
    cols = table() + [Column("f", "", "Y", formula=r"\ln(U)", gauss=True),
                      Column("g", "", "Y", formula="U^2*sin(I)", gauss=True)]
    assert recompute(cols) == {}
    by = {c.name: c for c in cols}
    assert by["Δf"].values[0] == pytest.approx(0.05)
    assert by["Δg"].values[0] == pytest.approx(math.hypot(4 * math.sin(3) * 0.1, 4 * math.cos(3) * 0.2))


def test_row_index_cycle_and_errors():
    cols = [Column("x", "", "X", [1.0, 2.0, 3.0]), Column("y", formula="0.5*i")]
    recompute(cols)
    assert cols[1].values == [0.5, 1.0, 1.5]
    cols = [Column("a", formula="b+1", values=[9.0]), Column("b", formula="a+1"),
            Column("c", formula="gone*2", values=[1.0])]
    assert set(recompute(cols)) == {"a", "b", "c"}
    assert cols[0].values == [] and cols[2].values == []
    cols = [Column("x", "", "X", [-1.0, 4.0]), Column("y", formula="sqrt(x)", gauss=True)]
    recompute(cols)
    assert cols[1].values == [None, 2.0] and cols[2].values == [None, 0.0]  # ohne Δx kein Fehler


def test_row_value():
    cols = table()
    assert row_value("U*I+i", cols, 1) == 22.0
    with pytest.raises(FormulaError):
        row_value("U*I", cols, 2)  # U leer


@pytest.mark.parametrize("old, new, factor", [
    ("mV", "V", 1e-3), ("V", "kV", 1e-3), ("µA", "nA", 1e3), ("uA", "µA", 1.0),
    ("m", "mm", 1e3), ("mol", "mmol", 1e3), ("kPa", "Pa", 1e3), ("cm²", "m²", 1e-4),
    ("mm^3", "m^3", 1e-9), ("cd", "mcd", 1e3), ("V", "A", None), ("m", "m²", None),
])
def test_prefix_factor(old, new, factor):
    f = prefix_factor(old, new)
    assert f == factor if factor is None else f == pytest.approx(factor, rel=1e-15)


def test_evaluate_vectorised():
    from kurvenwerk.formula import evaluate
    e = parse("2*x+1", ["x"])
    assert np.array_equal(evaluate(e, {"x": np.array([0.0, 1.0])}, 2), [1.0, 3.0])
    assert np.array_equal(evaluate(parse("pi"), {}, 3), [math.pi] * 3)
