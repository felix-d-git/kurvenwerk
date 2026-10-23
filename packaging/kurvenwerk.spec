# PyInstaller One-Folder-Build (LGPL: Qt-DLLs bleiben austauschbare Einzeldateien).
# Bau: pyinstaller packaging/kurvenwerk.spec --noconfirm  → dist/Kurvenwerk/
import re
import shutil
import sys
from importlib.metadata import distribution
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

HERE = Path(SPECPATH)
ROOT = HERE.parent

a = Analysis(
    [str(HERE / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("kurvenwerk"),
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "IPython", "pytest", "_pytest", "pygments"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Kurvenwerk", console=False, icon=str(HERE / "kurvenwerk.ico"))
COLLECT(exe, a.binaries, a.datas, name="Kurvenwerk")

# Lizenztexte neben die .exe: eigene, LGPL/GPL, Python und alle gebündelten Pakete
out = Path(DISTPATH) / "Kurvenwerk"
lic = out / "licenses"
shutil.copy(ROOT / "LICENSE", out / "LICENSE.txt")
shutil.copy(HERE / "THIRD_PARTY.txt", out)
shutil.copytree(HERE / "licenses", lic, dirs_exist_ok=True)
(lic / "Python").mkdir(exist_ok=True)
shutil.copy(Path(sys.base_prefix) / "LICENSE.txt", lic / "Python")


def deps(name, seen):
    d = distribution(name)
    key = d.metadata["Name"].lower()
    if key in seen:
        return
    seen[key] = d
    for req in d.requires or []:
        if "extra ==" not in req:
            sub = re.match(r"[A-Za-z0-9_.-]+", req).group(0)
            try:
                deps(sub, seen)
            except Exception:  # plattformfremde/optionale Pakete
                pass


seen = {}
deps("kurvenwerk", seen)
for key, d in seen.items():
    for f in d.files or []:
        if re.search(r"LICEN[CS]E|COPYING|NOTICE", f.name, re.I) and ".dist-info" in str(f):
            dst = lic / f"{d.metadata['Name']}-{d.version}" / Path(*f.parts[1:])
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f.locate(), dst)
