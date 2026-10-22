"""Paste-Parser: CSV/TSV/Excel-Text → Kopfzeilen + Spaltenwerte. Reine Logik, ohne Qt."""
import csv
import math
import re

DECIMALS = ("auto", ".", ",")
_HEADER = re.compile(r"^(.*?)\s*(?:/\s*(.*)|\[(.*)\])$")


def to_float(s: str, decimal: str = "auto") -> float | None:
    """Zahl aus Text; Tausendertrenner nur im Dreiergruppen-Muster. None = keine Zahl."""
    s = s.strip().replace("\u2212", "-")
    if not s or "_" in s:
        return None
    dec = decimal
    if dec == "auto":
        dec = "," if s.rfind(",") > s.rfind(".") else "."
    sep = "," if dec == "." else "."
    if sep in s:
        d, t = re.escape(dec), re.escape(sep)
        if not re.fullmatch(rf"[+-]?\d{{1,3}}({t}\d{{3}})+({d}\d*)?([eE][+-]?\d+)?", s):
            return None
        s = s.replace(sep, "")
    try:
        v = float(s.replace(dec, "."))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def parse_header(h: str) -> tuple[str, str]:
    """'U / mV' und 'U [mV]' → ('U', 'mV'); sonst (Text, '')."""
    h = h.strip()
    m = _HEADER.match(h)
    if not m or not m.group(1):
        return h, ""
    return m.group(1).strip(), (m.group(2) or m.group(3) or "").strip()


def _split(lines: list[str], delim: str | None) -> list[list[str]]:
    if delim is None:
        return [line.split() for line in lines]
    return [[f.strip() for f in row] for row in csv.reader(lines, delimiter=delim)]


def _is_header(row: list[str], decimal: str) -> bool:
    return any(f and to_float(f, decimal) is None for f in row)


def _fits(rows: list[list[str]], decimal: str) -> bool:
    data = rows[1:] if _is_header(rows[0], decimal) else rows
    return bool(data) and max(map(len, data)) >= 2 \
        and all(not f or to_float(f, decimal) is not None for r in data for f in r)


def _comma_column(lines: list[str]) -> bool:
    """Eine Spalte mit Dezimalkomma: jede Datenzeile eine Zahl mit höchstens einem Komma, keine Punkte."""
    data = lines[1:] if to_float(lines[0], ",") is None and "," not in lines[0] else lines
    data = [s.strip() for s in data if s.strip()]
    return any("," in s for s in data) and all(
        s.count(",") <= 1 and "." not in s and to_float(s, ",") is not None for s in data)


def parse(text: str, decimal: str = "auto"):
    """→ (headers, columns). headers: [(Größe, Einheit)] oder None; columns: Spalten mit float|None.

    Trennzeichen: Tab (Excel) immer; auto + eine Spalte '1,5' → Dezimalkomma; sonst erstes von
    ; , Leerraum, das ein sauberes Zahlenraster ergibt; sonst eine Spalte. Bei Dezimaltrenner
    Komma ist Komma kein Spaltentrenner. Leerzeilen innen bleiben als leere Zellen erhalten.
    """
    if decimal not in DECIMALS:
        raise ValueError(f"Dezimaltrenner {decimal!r} unbekannt")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():  # Leerzeilen innen bleiben (Excel-Lücken)
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return None, []
    if "\t" in text:
        delim, dec = "\t", decimal
    elif decimal == "auto" and _comma_column(lines):
        delim, dec = "single", ","  # eine Spalte '1,5' (Excel deutsch) statt CSV x=1, y=5
    else:
        delim, dec = "single", decimal
        for d in (";", ",", None):
            if d == "," and decimal == ",":
                continue
            fdec = "." if d == "," and decimal == "auto" else decimal
            if (d is None or d in text) and _fits(_split(lines, d), fdec):
                delim, dec = d, fdec
                break
    rows = [[line.strip()] for line in lines] if delim == "single" else _split(lines, delim)
    headers = None
    if _is_header(rows[0], dec):
        head, rows = rows[0], rows[1:]
        width = max((len(r) for r in rows), default=len(head))
        if delim is None and len(head) != width:  # Leerraum-getrennt: 'U / mV  I / µA'
            head = re.split(r"\s{2,}", lines[0].strip())
        headers = [parse_header(h) for h in head]
    width = max([len(r) for r in rows] + [len(headers or [])])
    cols = [[to_float(r[j], dec) if j < len(r) else None for r in rows] for j in range(width)]
    if headers:
        headers += [("", "")] * (width - len(headers))
    return headers, cols
