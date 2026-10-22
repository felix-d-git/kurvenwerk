# Kurvenwerk — Regeln für Agenten

Erst `GRUNDSAETZE.md` lesen. Lokale/private Zusatzregeln stehen in `CLAUDE.local.md` (nicht im Repo).

## Stack
Python 3.12, PySide6, Matplotlib (`FigureCanvasQTAgg`), numpy, scipy, sympy, openpyxl. Code unter `src/kurvenwerk/`.
Projektdatei = JSON mit `version`-Feld.

## Entwicklung
```
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python -m kurvenwerk
```

## Datenschutz (hart)
- Vor jedem Commit **und** Push: `.venv\Scripts\python scripts\check_privacy.py` → muss `Datenschutz-Check OK` melden.
- Pre-Push-Hook einrichten, falls `.git/hooks/pre-push` fehlt:
  `python scripts/check_privacy.py` als Hook (siehe `scripts/pre-push`).
- Nie: absolute Pfade, Nutzer-/Rechnernamen, echte Messdaten, Mail-Adressen, Tokens in Dateien oder Commit-Messages.
- Git-Identität im Repo nur die GitHub-noreply-Adresse.
- Vor Release: Check zusätzlich mit `--extra dist/Kurvenwerk <zip>` über die Build-Artefakte.

## Tests
- Logik (Parser, Fit, Statistik, Rundung, Fehlerfortpflanzung): je ein kleines `tests/test_*.py` mit Referenzwerten, Lauf: `.venv\Scripts\python -m pytest -q` bzw. `python -m unittest`.
- GUI-Tests (klicken, Screenshots) **nicht** selbst durchführen — als ⬜-Prüfschritt in die Projekt-TODO schreiben.
