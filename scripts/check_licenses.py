"""Lizenz-Gate: prüft alle Laufzeitabhängigkeiten von Kurvenwerk gegen die Freigabeliste.

    python scripts/check_licenses.py                  # Prüfung (CI, vor jedem Build/Release)
    python scripts/check_licenses.py --sbom bom.json  # zusätzlich CycloneDX-SBOM schreiben

Exit 1 bei nicht freigegebener oder unklarer Lizenz, fehlender Lizenzdatei oder wenn
packaging/licenses/Qt-ThirdParty.txt nicht zur installierten Qt-Version passt.
Wird auch von packaging/kurvenwerk.spec importiert (runtime_dists, license_files).
"""
import json
import re
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LICENSES = ROOT / "packaging" / "licenses"
QT_NOTICE = LICENSES / "Qt-ThirdParty.txt"

# GRUNDSAETZE §4: nur permissive Lizenzen
ALLOWED = {"MIT", "MIT-CMU", "BSD", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "ISC",
           "Apache-2.0", "PSF-2.0", "Zlib", "CC0-1.0"}
# Bewusste Ausnahme: Qt for Python unter LGPL-3.0 (One-Folder-Build, Qt-DLLs austauschbar).
# Nur Essentials — das Metapaket PySide6 zieht Addons/WebEngine/Pdf mit GPL-only-Modulen (#5).
LGPL_OK = {"pyside6-essentials", "shiboken6"}
# Wheels ohne brauchbare Lizenzdatei → Text liegt unter packaging/licenses/
# (PySide6/shiboken6 liefern nur den Qt-Commercial-Hinweis bzw. gar nichts)
MANUAL_LICENSE = {"antlr4-python3-runtime": "antlr4-python3-runtime/LICENSE.txt",
                  "pyside6-essentials": "LGPL-3.0.txt", "shiboken6": "LGPL-3.0.txt"}

CLASSIFIERS = {"MIT License": "MIT", "BSD License": "BSD", "Apache Software License": "Apache-2.0",
               "Python Software Foundation License": "PSF-2.0", "ISC License (ISCL)": "ISC"}
SPDX_EXPR = re.compile(r"^\(?[A-Za-z0-9.+-]+\)?(\s+(AND|OR)\s+\(?[A-Za-z0-9.+-]+\)?)*$")
LICENSE_FILE = re.compile(r"LICEN[CS]E|COPYING|NOTICE", re.I)


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_dists(root="kurvenwerk"):
    """Alle installierten Distributionen im Abhängigkeitsbaum von `root` (ohne Extras)."""
    seen = {}

    def walk(name):
        try:
            d = distribution(name)
        except PackageNotFoundError:  # plattformfremde/optionale Pakete
            return
        key = canonical(d.metadata["Name"])
        if key in seen:
            return
        seen[key] = d
        for req in d.requires or []:
            if "extra ==" not in req:
                walk(re.match(r"[A-Za-z0-9_.-]+", req).group(0))

    walk(root)
    return seen


def license_files(d):
    return [f for f in d.files or [] if ".dist-info" in str(f) and LICENSE_FILE.search(f.name)]


def license_of(metadata):
    """SPDX-Ausdruck aus License-Expression, kurzem License-Feld oder Classifiern; None = unklar."""
    if metadata.get("License-Expression"):
        return metadata["License-Expression"].strip()
    field = (metadata.get("License") or "").strip()
    if SPDX_EXPR.match(field):
        return field
    names = [c.split(" :: ")[-1] for c in metadata.get_all("Classifier") or []
             if c.startswith("License :: ")]
    if names:  # mehrere Classifier = Wahlmöglichkeit (z.B. python-dateutil)
        return " OR ".join(CLASSIFIERS.get(n, n.replace(" ", "-")) for n in names)
    return None


def allowed(expr, name=""):
    ok = ALLOWED | ({"LGPL-3.0-only"} if name in LGPL_OK else set())
    for alt in re.split(r"\s+OR\s+", expr):
        if all(t.strip("() ") in ok for t in re.split(r"\s+AND\s+", alt)):
            return True
    return False


def problems(dists):
    out = []
    for key, d in sorted(dists.items()):
        lic = license_of(d.metadata)
        if lic is None:
            out.append(f"{key} {d.version}: Lizenz UNKLAR")
        elif not allowed(lic, key):
            out.append(f"{key} {d.version}: Lizenz nicht freigegeben: {lic}")
        if key in MANUAL_LICENSE:
            if not (LICENSES / MANUAL_LICENSE[key]).is_file():
                out.append(f"{key}: packaging/licenses/{MANUAL_LICENSE[key]} fehlt")
        elif not license_files(d):
            out.append(f"{key} {d.version}: keine Lizenzdatei im Paket")
    return out


def qt_notice_problem():
    try:
        qt = distribution("PySide6-Essentials").version
    except PackageNotFoundError:
        return "PySide6-Essentials nicht installiert"
    first = QT_NOTICE.read_text(encoding="utf-8").split("\n", 1)[0] if QT_NOTICE.exists() else ""
    m = re.match(r"Qt (\d+\.\d+)", first)
    if not m or m.group(1) != ".".join(qt.split(".")[:2]):
        return (f"{QT_NOTICE.name} gilt für '{first[:20]}', installiert ist Qt {qt} — "
                "mit scripts/qt_third_party.py neu erzeugen und Attributionen prüfen")
    return None


def sbom(dists):
    def lic(expr):
        return [{"expression": expr}] if expr and expr != "BSD" else [{"license": {"name": expr or "UNKLAR"}}]

    me = dists.pop("kurvenwerk")
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {"type": "application", "name": "kurvenwerk", "version": me.version,
                                   "licenses": lic(license_of(me.metadata))}},
        "components": [{"type": "library", "name": d.metadata["Name"], "version": d.version,
                        "purl": f"pkg:pypi/{key}@{d.version}", "licenses": lic(license_of(d.metadata))}
                       for key, d in sorted(dists.items())],
    }


def main():
    dists = runtime_dists()
    if "kurvenwerk" not in dists:
        sys.exit("FEHLER: kurvenwerk nicht installiert (pip install -e .)")
    found = problems(dists)
    if qt := qt_notice_problem():
        found.append(qt)
    for key, d in sorted(dists.items()):
        print(f"  {key:28} {d.version:14} {license_of(d.metadata)}")
    if "--sbom" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--sbom") + 1])
        out.write_text(json.dumps(sbom(dict(dists)), indent=2) + "\n", encoding="utf-8")
        print(f"SBOM: {out.name}")
    if found:
        print("LIZENZ-CHECK FEHLGESCHLAGEN:")
        print("\n".join(f"  {p}" for p in found))
        sys.exit(1)
    print("Lizenz-Check OK")


if __name__ == "__main__":
    main()
