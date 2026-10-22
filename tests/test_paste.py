import pytest

from kurvenwerk.paste import parse, parse_header, to_float


@pytest.mark.parametrize("s, dec, v", [
    ("1.5", "auto", 1.5), ("1,5", "auto", 1.5), ("-2,5e-3", "auto", -2.5e-3),
    ("1.234,5", "auto", 1234.5), ("1,234.5", "auto", 1234.5), ("\u22123", "auto", -3.0),
    ("1,5", ".", None), ("1,234", ".", 1234.0), ("1.234", ",", 1234.0), ("2,25", ",", 2.25),
    ("", "auto", None), ("abc", "auto", None), ("1_0", "auto", None), ("nan", "auto", None),
    ("1.2.3", "auto", None),
])
def test_to_float(s, dec, v):
    assert to_float(s, dec) == v


@pytest.mark.parametrize("h, out", [
    ("U / mV", ("U", "mV")), ("U [mV]", ("U", "mV")), ("ΔI/µA", ("ΔI", "µA")),
    ("t", ("t", "")), ("T [°C]", ("T", "°C")), ("[mV]", ("[mV]", "")),
])
def test_parse_header(h, out):
    assert parse_header(h) == out


def test_excel_tsv_with_header_and_gap():
    h, cols = parse("U / mV\tI [µA]\r\n0,5\t1,25\r\n1,0\t\r\n", "auto")
    assert h == [("U", "mV"), ("I", "µA")]
    assert cols == [[0.5, 1.0], [1.25, None]]


def test_csv_comma_point_decimal():
    h, cols = parse("x,y\n1.5,2\n3,4.25\n")
    assert h == [("x", ""), ("y", "")] and cols == [[1.5, 3.0], [2.0, 4.25]]


def test_semicolon_comma_decimal():
    assert parse("1,5;2\n3;4,75") == (None, [[1.5, 3.0], [2.0, 4.75]])
    assert parse("a;b\n1;2;3\n4") == ([("a", ""), ("b", ""), ("", "")], [[1.0, 4.0], [2.0, None], [3.0, None]])


def test_whitespace_comma_decimal():
    h, cols = parse("U / mV   I / µA\n1,5 2,5\n3,5 4,5")
    assert h == [("U", "mV"), ("I", "µA")] and cols == [[1.5, 3.5], [2.5, 4.5]]


def test_ambiguous_comma_follows_setting():
    assert parse("1,5\r\n2\r\n2,5\r\n", "auto") == (None, [[1.5, 2.0, 2.5]])  # Excel-Spalte, deutsch
    assert parse("U / mV\n1,5\n2,5") == ([("U", "mV")], [[1.5, 2.5]])
    assert parse("1,5\n2,5", ".") == (None, [[1.0, 2.0], [5.0, 5.0]])
    assert parse("1,5,7\n2,5,8") == (None, [[1.0, 2.0], [5.0, 5.0], [7.0, 8.0]])  # CSV
    assert parse("x,y\n1,5\n2,5") == ([("x", ""), ("y", "")], [[1.0, 2.0], [5.0, 5.0]])


def test_inner_blank_lines_kept():
    assert parse("\n1\n2\n\n3\n\n") == (None, [[1.0, 2.0, None, 3.0]])
    assert parse("1\t2\n\t\n3\t4\r\n") == (None, [[1.0, None, 3.0], [2.0, None, 4.0]])


def test_single_column_and_empty():
    assert parse("1\n2\n3") == (None, [[1.0, 2.0, 3.0]])
    assert parse("") == (None, [])
    with pytest.raises(ValueError):
        parse("1", "x")
