"""Erzeugt packaging/licenses/Qt-ThirdParty.txt aus den qt_attribution.json der Qt-Quellen.

Aufruf (offline, liest nur lokale Checkouts desselben Qt-Tags wie PySide6-Essentials):
    python scripts/qt_third_party.py 6.12.0 <qtbase> <qtsvg> <qtimageformats> > packaging/licenses/Qt-ThirdParty.txt

Aufgenommen wird, was in einem Windows-Build von QtCore/QtGui/QtWidgets/QtSvg und den
mitgelieferten Plugins (platforms, styles, imageformats, iconengines) stecken kann.
Lieber eine Komponente zu viel als eine zu wenig.
"""
import json
import re
import sys
from pathlib import Path

# Nicht Teil des Windows-Builds bzw. Module, die Kurvenwerk nicht ausliefert
SKIP_PATH = re.compile(r"[\\/](cmake|tests?|util|testlib|wayland|xcb|android|gradle|wasm|libpsl|sqlite|dbus)[\\/]"
                       r"|plugins[\\/]platforms[\\/]cocoa")
SKIP_ID = {"forkfd", "pixman", "qeventdispatcher_cf"}  # Unix / ARM NEON / macOS


def entries(root):
    for f in sorted(Path(root).rglob("qt_attribution.json")):
        if SKIP_PATH.search(str(f.relative_to(root.parent))):
            continue
        data = json.loads(f.read_text(encoding="utf-8"), strict=False)
        for e in data if isinstance(data, list) else [data]:
            if e.get("Id") not in SKIP_ID:
                yield f.parent, e


def read(base, name):
    p = (base / name).resolve()
    if not p.is_file():
        sys.exit(f"Fehlt im Checkout: {p.name} ({base.name})")
    return p.read_text(encoding="utf-8", errors="replace").strip()


def block(base, e, licenses_dir):
    files = e.get("LicenseFiles") or ([e["LicenseFile"]] if e.get("LicenseFile") else [])
    if files:
        texts = [read(base, n) for n in files]
    else:  # nur SPDX-Id angegeben → Standardtext aus LICENSES/
        ids = [t for t in re.split(r"[\s()]+", e["LicenseId"]) if t and t not in ("AND", "OR", "WITH")]
        texts = [read(licenses_dir, f"{i}.txt") for i in ids]
    copyright = e.get("Copyright")
    if isinstance(copyright, list):
        copyright = "\n".join(copyright)
    if e.get("CopyrightFile"):
        copyright = read(base, e["CopyrightFile"])
    head = [e["Name"] + (f" {e['Version']}" if e.get("Version") else ""),
            "=" * 72,
            f"Verwendung in Qt: {' '.join(e.get('QtUsage', '').split())}",
            f"Lizenz: {e['LicenseId']}"]
    if e.get("Homepage"):
        head.append(f"Homepage: {e['Homepage']}")
    if copyright:
        head += ["", copyright.strip()]
    return "\n".join(head + [""] + texts)


def main():
    version, roots = sys.argv[1], [Path(r).resolve() for r in sys.argv[2:]]
    licenses_dir = roots[0] / "LICENSES"
    out = [f"Qt {version} — Komponenten Dritter",
           "=" * 72,
           "Qt enthält die folgenden Komponenten Dritter. Erzeugt mit scripts/qt_third_party.py",
           f"aus den qt_attribution.json der Qt-Quellen (Tag v{version}): "
           + ", ".join(r.name for r in roots) + ".",
           "",
           "This software is based in part on the work of the Independent JPEG Group.",
           "Portions of this software are copyright © The FreeType Project (www.freetype.org).",
           "All rights reserved.",
           ""]
    seen = set()
    for root in roots:
        for base, e in entries(root):
            if e["Id"] not in seen:
                seen.add(e["Id"])
                out += ["", block(base, e, licenses_dir), ""]
    sys.stdout.write("\n".join(out).rstrip() + "\n")


if __name__ == "__main__":
    main()
