"""Ergebnisse runden und als Text bzw. siunitx (v3: \\num, \\qty, \\unit) ausgeben.
DIN 1333: Unsicherheit aufrunden auf 2 gültige Ziffern bei führender 1 oder 2, sonst auf 1;
Wert kaufmännisch auf dieselbe Stelle. Rechnet in Decimal, damit 0.012 nicht durch 0.0120000001 auf 0.013 springt."""
import math
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation, localcontext


def _dec(v: float) -> Decimal:
    return Decimal(repr(float(v)))  # repr = kürzeste Darstellung; float() wegen np.float64-repr


def din(v: float, e: float) -> tuple[Decimal, Decimal]:
    """(Wert, Unsicherheit) nach DIN 1333 gerundet."""
    v, e = _dec(v), _dec(abs(e))
    lead = e.adjusted()
    q = Decimal(1).scaleb(lead - (2 if int(e.scaleb(-lead)) <= 2 else 1) + 1)
    with localcontext(prec=60):
        return v.quantize(q, ROUND_HALF_UP), e.quantize(q, ROUND_CEILING)


def _exp(v: float, e: float) -> int:
    """Gemeinsamer Zehnerexponent bei sehr großen/kleinen Zahlen, sonst 0."""
    k = _dec(max(abs(v), e)).adjusted()
    return 0 if -3 <= k <= 4 else k


def num(v: float, e: float | None = None, rounded: bool = True, tex: bool = False) -> str:
    """Zahl ohne Einheit. tex → Inhalt für \\num{…} bzw. eine siunitx-S-Spalte."""
    pm = r" \pm " if tex else " ± "
    ok = e is not None and math.isfinite(v) and math.isfinite(e) and e > 0
    if not (ok and rounded):
        s = f"{v:.6g}" if e is None else f"{v:.6g}{pm}{e:.2g}"
        return s.replace("inf", r"\infty") if tex else s
    k = _exp(v, e)
    try:
        rv, re_ = din(v / 10 ** k, e / 10 ** k)
    except InvalidOperation:  # Unsicherheit um > 50 Stellen kleiner als der Wert
        return num(v, e, False, tex)
    s = f"{rv:f}{pm}{re_:f}"
    if not k:
        return s
    return f"{s} e{k}" if tex else f"({s})e{k}"


def _value(v: float, e: float, rounded: bool) -> str:
    """Nur der Wert, auf die DIN-Stelle der Unsicherheit gerundet (mit Exponent)."""
    if rounded:
        k = _exp(v, e)
        try:
            return f"{din(v / 10 ** k, e / 10 ** k)[0]:f}" + (f"e{k}" if k else "")
        except InvalidOperation:
            pass
    return f"{v:.6g}"


def fmt(v: float, e: float | None = None, rounded: bool = True, tex: bool = False, unit: str = "",
        pct: bool = False) -> str:
    """Zahl mit Einheit: Text `(1.23 ± 0.05) mV` bzw. `\\qty{1.23 \\pm 0.05}{mV}`.
    pct → relative Unsicherheit: `1.23 mV ± 4.1 %` bzw. `\\qty{1.23}{mV} $\\pm$ \\qty{4.1}{\\percent}`;
    der Prozentwert wird wie eine Unsicherheit nach DIN aufgerundet."""
    if pct and e is not None and math.isfinite(v) and math.isfinite(e) and e > 0 and v:
        rel = 100 * e / abs(v)
        r, a = f"{din(0, rel)[1]:f}" if rounded else f"{rel:.2g}", _value(v, e, rounded)
        if tex:
            return (rf"\qty{{{a}}}{{{unit}}}" if unit else rf"\num{{{a}}}") + rf" $\pm$ \qty{{{r}}}{{\percent}}"
        return f"{a}{' ' + unit if unit else ''} ± {r} %"
    n = num(v, e, rounded, tex)
    if tex:
        return rf"\qty{{{n}}}{{{unit}}}" if unit else rf"\num{{{n}}}"
    if not unit:
        return n
    return f"({n}) {unit}" if "±" in n and not n.startswith("(") else f"{n} {unit}"
