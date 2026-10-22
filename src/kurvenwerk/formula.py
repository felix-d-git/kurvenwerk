"""Formeln: Text/LaTeX/Markdown → sympy → numpy (lambdify). Kein eval auf Nutzertext:
Text wird erst gegen eine Token-Whitelist geprüft (nur Zahlen, Operatoren, bekannte Namen),
dann von parse_expr mit festem Namensraum gelesen; LaTeX geht über parse_latex (ANTLR)."""
import re
from graphlib import CycleError, TopologicalSorter

import numpy as np
import sympy as sp
from sympy.parsing.latex import parse_latex
from sympy.parsing.sympy_parser import (convert_xor, implicit_multiplication, parse_expr,
                                        standard_transformations)

from .model import Column

ROW = "i"  # Zeilennummer ab 1, falls keine Spalte so heißt
FUNCS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "atan2": sp.atan2, "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "exp": sp.exp,
    "ln": sp.log, "log": sp.log, "log10": lambda x: sp.log(x, 10), "lg": lambda x: sp.log(x, 10),
    "sqrt": sp.sqrt, "abs": sp.Abs,
}
CONSTS = {"pi": sp.pi, "e": sp.E}
_TOKEN = re.compile(r"\s+|(?P<num>(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?)|(?P<name>[^\W\d]\w*)|\*\*|[-+*/^(),]")
_GLOBALS = {"__builtins__": {}, "Integer": sp.Integer, "Float": sp.Float, "Rational": sp.Rational,
            "Symbol": sp.Symbol}
_TRANSFORMS = standard_transformations + (implicit_multiplication, convert_xor)


class FormulaError(ValueError):
    pass


def _namespace(names) -> dict:
    ns = {**FUNCS, **CONSTS, ROW: sp.Symbol(ROW)}
    ns.update({n: sp.Symbol(n) for n in names})  # Spaltennamen haben Vorrang
    return ns


def _latex(text: str, ns: dict) -> sp.Expr:
    try:
        expr = parse_latex(text)
    except Exception as e:  # ANTLR-Fehler sind keine einheitliche Klasse
        raise FormulaError(f"LaTeX nicht lesbar: {e}") from None
    subs = {}
    for s in expr.free_symbols:
        n = s.name.replace("{", "").replace("}", "")
        if n not in ns or callable(ns[n]):
            raise FormulaError(f"Unbekannter Name: {n}")
        subs[s] = ns[n]
    return expr.xreplace(subs)


def parse(text: str, names=()) -> sp.Expr:
    """Formel → sympy-Ausdruck. names = erlaubte Variablen (Spaltennamen).
    LaTeX bei `\\`, `{` oder `$…$` (Markdown), sonst Text mit `^` oder `**` als Potenz."""
    text = text.strip()
    if text.startswith("$") and text.endswith("$"):
        text = text.strip("$").strip()
    if not text:
        raise FormulaError("Leere Formel")
    ns = _namespace(names)
    if "\\" in text or "{" in text:
        return _latex(text, ns)
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise FormulaError(f"Unerlaubtes Zeichen: {text[pos]!r}")
        if m["name"] and m["name"] not in ns:
            raise FormulaError(f"Unbekannter Name: {m['name']}")
        pos = m.end()
    try:
        expr = parse_expr(text, local_dict=ns, global_dict=dict(_GLOBALS), transformations=_TRANSFORMS)
    except Exception as e:  # SyntaxError, TypeError (z.B. Spalte als Funktion) …
        raise FormulaError(f"Formel nicht lesbar: {text}") from e
    if not isinstance(expr, sp.Expr):
        raise FormulaError(f"Kein Rechenausdruck: {text}")
    return expr


def number(text: str) -> float:
    """Konstanter Ausdruck ('1e-3', '1/3', '2pi') → float."""
    v = complex(parse(text).evalf())
    if v.imag or not np.isfinite(v.real):
        raise FormulaError(f"Keine reelle Zahl: {text}")
    return v.real


def evaluate(expr: sp.Expr, data: dict[str, np.ndarray], n: int) -> np.ndarray:
    syms = sorted(expr.free_symbols, key=lambda s: s.name)
    f = sp.lambdify(syms, expr, "numpy")
    with np.errstate(all="ignore"):
        r = np.asarray(f(*(data[s.name] for s in syms)), dtype=complex)
    r = np.where(r.imag == 0, r.real, np.nan)  # komplexe Ergebnisse → leer
    return np.broadcast_to(r, (n,)).astype(float)


def propagate(expr: sp.Expr, data: dict[str, np.ndarray], errors: dict[str, np.ndarray], n: int):
    """→ (Wert, Gauß-Fehler) mit Δf = √Σ (∂f/∂x · Δx)², Eingänge als unkorreliert angenommen."""
    var = 0.0
    for s in expr.free_symbols:
        if s.name in errors:
            var = var + (evaluate(sp.diff(expr, s), data, n) * errors[s.name]) ** 2
    val = evaluate(expr, data, n)
    return val, np.where(np.isfinite(val), np.sqrt(var), np.nan)


# --- Spalten einer Tabelle ---

def _array(vals, n: int) -> np.ndarray:
    a = np.full(n, np.nan)
    a[:len(vals)] = [np.nan if v is None else v for v in vals[:n]]
    return a


def _values(a: np.ndarray) -> list[float | None]:
    return [float(v) if np.isfinite(v) else None for v in a]


def error_column(cols: list[Column], name: str) -> Column | None:
    return next((c for c in cols if c.name == "Δ" + name and c.role.startswith("Δ")), None)


def row_value(text: str, cols: list[Column], row: int) -> float:
    """Zellformel '=…' für eine Zeile: Spaltennamen stehen für die Werte dieser Zeile."""
    expr = parse(text, [c.name for c in cols])
    data = {c.name: _array(c.values[row:row + 1], 1) for c in cols}
    data.setdefault(ROW, np.array([row + 1.0]))
    v = evaluate(expr, data, 1)[0]
    if not np.isfinite(v):
        raise FormulaError("Ergebnis ist keine Zahl")
    return float(v)


def recompute(cols: list[Column]) -> dict[str, str]:
    """Berechnete Spalten (formula) neu füllen, abhängige nach ihren Quellen; mit gauss=True
    landet der Gauß-Fehler in Δ<Name> (wird angelegt). → {Spaltenname: Fehlermeldung}."""
    by = {c.name: c for c in cols}
    calc = {c.name: c for c in cols if c.formula}
    exprs, failed, order = {}, {}, {}
    for name, c in calc.items():
        try:
            exprs[name] = parse(c.formula, by)
        except FormulaError as e:
            failed[name] = str(e)
            continue
        refs = {s.name for s in exprs[name].free_symbols}
        order[name] = {r for r in refs | {r[1:] for r in refs if r.startswith("Δ")} if r in calc} - {name}
    try:
        names = list(TopologicalSorter(order).static_order())
    except CycleError:
        names, failed = [], failed | {n: "Zirkelbezug" for n in exprs}
    for name in names:
        if name in failed or name not in exprs:
            continue
        c, expr = calc[name], exprs[name]
        refs = [by[s.name] for s in expr.free_symbols if s.name in by]
        n = max((len(r.values) for r in refs), default=0) or \
            max((len(k.values) for k in cols if not k.formula), default=0)
        data = {k.name: _array(k.values, n) for k in cols}
        data.setdefault(ROW, np.arange(1.0, n + 1))
        errs = {r.name: _array(e.values, n) for r in refs if (e := error_column(cols, r.name))}
        val, err = propagate(expr, data, errs, n)
        c.values = _values(val)
        if c.gauss:
            e = error_column(cols, name)
            if e is None:
                e = Column("Δ" + name, c.unit, "Δx" if c.role == "X" else "Δy")
                cols.insert(cols.index(c) + 1, e)
                by[e.name] = e
            e.values = _values(err)
    for name in failed:
        calc[name].values = []  # nicht stehen lassen, was nicht mehr stimmt
    return failed


# --- Einheiten ---

PREFIX = {"": 0, "Q": 30, "R": 27, "Y": 24, "Z": 21, "E": 18, "P": 15, "T": 12, "G": 9, "M": 6,
          "k": 3, "h": 2, "da": 1, "d": -1, "c": -2, "m": -3, "µ": -6, "μ": -6, "u": -6, "n": -9,
          "p": -12, "f": -15, "a": -18, "z": -21, "y": -24, "r": -27, "q": -30}
_POWER = re.compile(r"^(.+?)(?:\^(-?\d+)|([²³]))?$")


def _splits(unit: str):
    m = _POWER.match(unit.strip())
    if not m:
        return
    base, p = m[1], int(m[2]) if m[2] else {"²": 2, "³": 3}.get(m[3], 1)
    for pre, exp in PREFIX.items():
        if base.startswith(pre) and len(base) > len(pre):
            yield base[len(pre):], exp, p


def prefix_factor(old: str, new: str) -> float | None:
    """Faktor für Werte bei Einheitenwechsel nur im SI-Präfix ('mV'→'V' = 1e-3), sonst None."""
    for bo, eo, po in _splits(old):
        for bn, en, pn in _splits(new):
            if bo == bn and po == pn:
                return 10.0 ** ((eo - en) * po)
    return None
