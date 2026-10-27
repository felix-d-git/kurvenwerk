import importlib.util
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_licenses", ROOT / "scripts" / "check_licenses.py")
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)


def meta(**fields):
    m = Message()
    for k, v in fields.items():
        for item in v if isinstance(v, list) else [v]:
            m[k.replace("_", "-")] = item
    return m


@pytest.mark.parametrize("expr, name, ok", [
    ("MIT", "", True),
    ("BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0", "", True),  # numpy
    ("Apache-2.0 OR BSD-2-Clause", "", True),                          # packaging
    ("GPL-3.0-only", "", False),
    ("MIT AND GPL-3.0-only", "", False),
    ("MPL-2.0", "", False),
    ("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", "pyside6-essentials", True),
    ("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", "pyside6-addons", False),  # Metapaket-Teil
    ("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", "pyside6", False),
])
def test_allowed(expr, name, ok):
    assert cl.allowed(expr, name) is ok


def test_license_of_reihenfolge():
    # License-Expression schlägt alles andere
    assert cl.license_of(meta(License_Expression="MIT-CMU", License="HPND")) == "MIT-CMU"
    # kurzes License-Feld (antlr4, sympy)
    assert cl.license_of(meta(License="BSD")) == "BSD"
    # langer Lizenztext im Feld → Classifier (scipy, matplotlib)
    assert cl.license_of(meta(License="Copyright (c) 2001\nAll rights reserved.",
                              Classifier="License :: OSI Approved :: BSD License")) == "BSD"
    assert cl.license_of(meta(Classifier="License :: OSI Approved :: Python Software Foundation License")) == "PSF-2.0"
    # Dual-Lizenz über zwei Classifier (python-dateutil)
    assert cl.license_of(meta(License="Dual License", Classifier=[
        "License :: OSI Approved :: BSD License",
        "License :: OSI Approved :: Apache Software License"])) == "BSD OR Apache-2.0"
    # unbekannter Classifier fällt durch, fehlende Angabe ist UNKLAR
    assert not cl.allowed(cl.license_of(meta(Classifier="License :: OSI Approved :: GNU General Public License v3 (GPLv3)")))
    assert cl.license_of(meta()) is None
