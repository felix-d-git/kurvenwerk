# Kurvenwerk

Desktop-Tool zum Erfassen, Auswerten und Plotten von Messwerten.
Tabellen mit Größe, Einheit und Unsicherheiten, freie Fit-Funktionen (auch in LaTeX-Schreibweise),
Statistik (Mittelwert, Standardabweichung, R², p-Wert, χ²) und Plots, die direkt aus Matplotlib kommen.

> Status: in Entwicklung, noch kein Release.

## Installation

**Nutzer (Windows):** unter *Releases* die `Kurvenwerk-<version>.zip` laden, entpacken, `Kurvenwerk.exe` starten.
Python wird nicht benötigt.

**Entwicklung:**

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python -m kurvenwerk
```

## Lizenz

MIT, siehe [LICENSE](LICENSE). Verwendete Bibliotheken behalten ihre eigenen Lizenzen
(u.a. PySide6/Qt: LGPL-3.0, Matplotlib, NumPy, SciPy, SymPy: BSD-artig).
Gebündelte Schriften Manrope und IBM Plex Mono: SIL Open Font License 1.1,
siehe `src/kurvenwerk/style/fonts/OFL-*.txt`.
