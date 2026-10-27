# Grundsätze

Jede Änderung muss die Prüffrage ihres Abschnitts bestehen. Die Fragen lassen sich an einem Diff beantworten.

## 1. Privat
Messdaten verlassen den Rechner nicht. Kein Netzwerkzugriff zur Laufzeit: keine Telemetrie,
kein Update-Check, keine Schrift vom CDN, kein Fehlerdienst.
→ **Spricht das eine Adresse an?**

## 2. Keine persönlichen Daten im Repo
Keine Nutzernamen, Rechnernamen, absoluten Pfade, echten Messdaten, E-Mail-Adressen oder Tokens
in Code, Tests, Commits oder Build-Artefakten. Testdaten sind synthetisch.
`python scripts/check_privacy.py` muss vor jedem Commit und Push grün sein (Pre-Push-Hook),
vor einem Release zusätzlich mit `--extra dist/ <release>.zip`.
→ **Würde ich diese Zeile einem Fremden zeigen?**

## 3. Kein `eval`
Formeln aus Nutzereingaben laufen ausschließlich über sympy (`parse_expr` mit festem Namensraum,
`parse_latex`) → `lambdify`. Nie `eval`/`exec` auf Nutzertext.
→ **Kann eine Formel Code ausführen?**

## 4. Rechtlich sauber
Kein übernommener Fremdcode. Neue Abhängigkeiten nur bei echtem Komplexitätsgewinn und nur
MIT/BSD/Apache-2.0. Bewusste Ausnahme: PySide6-Essentials (LGPL-3.0) — deshalb One-Folder-Build,
Qt-DLLs bleiben austauschbar; nie das Metapaket `PySide6` (zieht GPL-only-Module).
`python scripts/check_licenses.py` muss grün sein.
→ **Woher stammt dieser Code, und was hängt lizenzrechtlich daran?**

## 5. Eigenes Design
Farben, Radien und Schriften nur aus den Tokens in `src/kurvenwerk/style/`. Schriften lokal gebündelt.
→ **Erkennt man an drei Screenshots, dass das dieselbe App ist?**

## 6. Es muss rechnen
Fertig heißt: Self-Checks grün (`python -m pytest -q` über `tests/`). Fit, Statistik,
Rundung und Fehlerfortpflanzung werden gegen bekannte Referenzwerte geprüft, nicht gegen sich selbst.
→ **Schlägt die Prüfung ohne den Fix fehl?**

## 7. Nachvollziehbar
Besondere Vorsicht bei Diffs an Konfiguration, Abhängigkeiten, Build-Schritten und Workflows:
Netzwerkaufrufe, `eval`, `subprocess`, Zugriffe auf Zugangsdaten durchsehen.
