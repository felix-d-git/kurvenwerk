"""DIN-1333-Rundung gegen Hand-Beispiele, Text/siunitx-Ausgabe."""
from kurvenwerk.rounding import fmt, num


def test_din_rules():
    assert num(1.23456, 0.0123) == "1.235 ± 0.013"  # führende 1 → 2 Ziffern, aufrunden
    assert num(1.23456, 0.012) == "1.235 ± 0.012"  # exakt 0.012 bleibt (kein Float-Aufrunden)
    assert num(1.23456, 0.0291) == "1.235 ± 0.030"  # führende 2 → 2 Ziffern
    assert num(1.23456, 0.031) == "1.23 ± 0.04"  # führende 3 → 1 Ziffer, aufrunden
    assert num(1.225, 0.05) == "1.23 ± 0.05"  # Wert kaufmännisch (half up)
    assert num(9.87, 0.951) == "9.9 ± 1.0"
    assert num(1234.5, 36) == "1230 ± 40"
    assert num(-0.5, 0.25) == "-0.50 ± 0.25"


def test_exponent_and_off():
    assert num(1.2345e-7, 3.1e-9) == "(1.23 ± 0.04)e-7"
    assert num(1.2345e-7, 3.1e-9, tex=True) == r"1.23 \pm 0.04 e-7"
    assert num(1.23456, 0.0123, rounded=False) == "1.23456 ± 0.012"
    assert num(2.5) == "2.5" and num(2.5, 0) == "2.5 ± 0"


def test_fmt_units():
    assert fmt(1.23456, 0.0123, unit="mV") == "(1.235 ± 0.013) mV"
    assert fmt(1.23456, 0.0123, tex=True, unit="mV") == r"\qty{1.235 \pm 0.013}{mV}"
    assert fmt(3.0, tex=True) == r"\num{3}"
    assert fmt(1.2345e-7, 3.1e-9, unit="A") == "(1.23 ± 0.04)e-7 A"


def test_percent():
    assert fmt(2.0, 0.05, pct=True) == "2.00 ± 2.5 %"
    assert fmt(1.23456, 0.0123, unit="mV", pct=True) == "1.235 mV ± 1.0 %"  # 0.996 % → aufgerundet
    assert fmt(1.23e-7, 4e-9, pct=True) == "1.23e-7 ± 4 %"  # 3.25 % → 4 %
    assert fmt(2.0, 0.05, tex=True, unit="V", pct=True) == r"\qty{2.00}{V} $\pm$ \qty{2.5}{\percent}"
    assert fmt(2.0, 0.05, rounded=False, pct=True) == "2 ± 2.5 %"
    assert fmt(2.0, None, pct=True) == "2"
    assert fmt(0.0, 0.1, pct=True) == "0.00 ± 0.10"  # Wert 0 → absolut
