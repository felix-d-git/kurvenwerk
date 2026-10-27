# PyInstaller One-Folder-Build (LGPL: Qt-DLLs bleiben austauschbare Einzeldateien).
# Bau: pyinstaller packaging/kurvenwerk.spec --noconfirm  → dist/Kurvenwerk/
import re
import shutil
import sys
from importlib.metadata import distribution, version
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

HERE = Path(SPECPATH)
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_licenses import MANUAL_LICENSE, license_files, problems, runtime_dists  # noqa: E402

# Nur LGPL-Qt (Core/Gui/Widgets/Svg) ausliefern. Raus: Qt Virtual Keyboard (GPL-3.0-only),
# Qt PDF (PDFium), Qml/Quick/Network samt TLS-Plugins, OpenSSL vom Build-Host (die Python-eigenen
# libssl-3-x64/libcrypto-3-x64 bleiben) und Software-OpenGL (Mesa).
DROP = re.compile(r"virtualkeyboard|qtvkb|qpdf|Qt6Pdf|WebEngine|Qt6Quick|Qt6Qml|Qt6Network|QtNetwork\."
                  r"|plugins[\\/]tls[\\/]|(^|[\\/])lib(ssl|crypto)-3\.dll$|opengl32sw", re.I)

a = Analysis(
    [str(HERE / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("kurvenwerk"),
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "IPython", "pytest", "_pytest", "pygments",
              "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
)
a.binaries = [b for b in a.binaries if not DROP.search(b[0])]
a.datas = [d for d in a.datas if not DROP.search(d[0])]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Kurvenwerk", console=False, icon=str(HERE / "kurvenwerk.ico"))
COLLECT(exe, a.binaries, a.datas, name="Kurvenwerk")

out = Path(DISTPATH) / "Kurvenwerk"
bad = sorted(str(p.relative_to(out)) for p in out.rglob("*") if DROP.search(str(p.relative_to(out))))
if bad:
    sys.exit("Nicht freigegebene Komponenten im Build:\n  " + "\n  ".join(bad))

# Lizenztexte neben die .exe: eigene, LGPL/GPL/Apache, Qt-Dritte, Python, PyInstaller und alle Pakete
dists = runtime_dists()
if found := problems(dists):
    sys.exit("Lizenz-Check fehlgeschlagen:\n  " + "\n  ".join(found))
qt = version("PySide6-Essentials")
lic = out / "licenses"
shutil.copy(ROOT / "LICENSE", out / "LICENSE.txt")
notice = (HERE / "THIRD_PARTY.txt").read_text(encoding="utf-8")
notice = notice.replace("@QT_VERSION@", qt).replace("@QT_SERIES@", ".".join(qt.split(".")[:2]))
(out / "THIRD_PARTY.txt").write_text(notice, encoding="utf-8")
shutil.copytree(HERE / "licenses", lic, dirs_exist_ok=True)
(lic / "Python").mkdir(exist_ok=True)
shutil.copy(Path(sys.base_prefix) / "LICENSE.txt", lic / "Python")


def copy_licenses(d):
    for f in license_files(d):
        dst = lic / f"{d.metadata['Name']}-{d.version}" / Path(*f.parts[1:])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f.locate(), dst)


for key, d in dists.items():
    if key not in MANUAL_LICENSE:  # PySide6-Wheels: nur Qt-Commercial-Hinweis, LGPL liegt in licenses/
        copy_licenses(d)
copy_licenses(distribution("pyinstaller"))  # Bootloader + Runtime-Hooks stecken in Kurvenwerk.exe
