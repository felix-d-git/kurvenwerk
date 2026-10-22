# Kurvenwerk

Desktop-Tool zum Erfassen, Auswerten und Plotten von Messwerten.
Tabellen mit Größe, Einheit und Unsicherheiten, freie Fit-Funktionen (auch in LaTeX-Schreibweise),
Statistik (Mittelwert, Standardabweichung, R², p-Wert, χ²) und Plots, die direkt aus Matplotlib kommen.

<!-- Screenshot folgt: docs/screenshot.png -->

## Installation

**Nutzer (Windows):** unter [Releases](../../releases) die `Kurvenwerk-<version>.zip` laden, entpacken,
`Kurvenwerk\Kurvenwerk.exe` starten. Python wird nicht benötigt. Den Ordner nicht auseinanderreißen —
die `.exe` braucht `_internal\` daneben.

**Entwicklung:**

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python -m kurvenwerk
.venv\Scripts\python -m pytest -q
```

**Selbst bauen** (One-Folder, Ergebnis in `dist\Kurvenwerk\`):

```
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller packaging\kurvenwerk.spec --noconfirm
```

Releases baut GitHub Actions automatisch beim Push eines Tags `v*`.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Verwendete Bibliotheken behalten ihre eigenen Lizenzen
(u.a. PySide6/Qt: LGPL-3.0, Matplotlib, NumPy, SciPy, SymPy: BSD-artig).
Gebündelte Schriften Manrope und IBM Plex Mono: SIL Open Font License 1.1,
siehe `src/kurvenwerk/style/fonts/OFL-*.txt`.

Das Release-ZIP enthält `THIRD_PARTY.txt` und unter `licenses\` die Lizenztexte aller gebündelten
Pakete. Die Qt-/PySide6-Bibliotheken liegen als einzelne, austauschbare Dateien in
`_internal\PySide6\` und `_internal\shiboken6\` (LGPL-3.0).
