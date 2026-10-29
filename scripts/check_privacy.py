"""Datenschutz-Check: blockiert Commits/Pushes/Releases mit persönlichen Daten.

Prüft
  1. alle getrackten + gestagten Dateien (Inhalt + Pfad),
  2. die komplette Git-History (alle Blobs, Commit-Messages, Autor/Committer),
  3. optional Verzeichnisse/ZIPs (Build-Artefakte, SBOM): --extra dist/ Kurvenwerk.zip bom.json

Muster = generische Regexe hier + private Begriffe aus `.privacy-patterns.txt`
(gitignored, eine Regex pro Zeile, # = Kommentar). Exit 1 bei Treffer.
"""
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".privacy-patterns.txt"

# github.com: Bot-Adressen wie dependabot[bot] <support@github.com> im Signed-off-by
MAIL = r"[\w.+-]+@(?!users\.noreply\.github\.com|github\.com\b|anthropic\.com|example\.(?:com|org))[\w-]+\.[\w.]+"
KEY = r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
GENERIC = [
    r"[A-Za-z]:[\\/]+Users[\\/]++(?!runneradmin\b)",  # Windows-Nutzerpfade
    r"/home/[a-z]",                                 # Linux-Nutzerpfade
    MAIL,                                           # E-Mails
    r"\bgh[pousr]_[A-Za-z0-9]{30,}",                # GitHub-Token
    r"\bsk-[A-Za-z0-9_-]{20,}",                     # API-Keys
    KEY,
    r"(?i)\b(password|passwort|secret|api_key|token)\s*[:=]\s*['\"][^'\"\n]{6,}",
]
ALLOWED_AUTHOR = re.compile(r"(@users\.noreply\.github\.com|noreply@anthropic\.com|noreply@github\.com)$")
# Unveränderte Fremd-Lizenztexte: Copyright-Hinweise samt Autoren-Mail dürfen nicht gekürzt werden.
# Dort gelten die Artefakt-Regeln (keine generische Mail-Regel, private Muster weiterhin aktiv).
THIRD_PARTY_TEXTS = "packaging/licenses/"
SKIP_SUFFIX = {".png", ".ico", ".ttf", ".otf", ".woff", ".woff2", ".pdf", ".dll", ".pyd", ".exe", ".so"}

# Build-Artefakte (--extra) enthalten Fremd-Binärdateien. Dort gilt:
# - keine generische Mail-Regel (öffentliche Autoren-Mails in Python/OpenSSL/...); eigene Mail
#   fängt .privacy-patterns.txt,
# - Schlüssel nur mit Inhalt (Qt/OpenSSL enthalten die PEM-Kopfzeile als Formatkonstante),
# - eng umrissene, bekannte Fremd-Strings werden vor der Suche entfernt (Rest des Strings wird geprüft).
ARTIFACT_ALLOW = re.compile("|".join([
    r"[A-Za-z]:[\\/]+Users[\\/]+qt[\\/]+work[\\/]",     # Build-Pfade der offiziellen Qt-Binaries
    r"splitroot\('C:/Users/Barney'\)",                  # Docstring-Beispiel in ntpath (Python-Stdlib)
    r"publicKeyToken=\"[0-9a-f]{16}\"",                 # Windows-Manifest (Common Controls)
    r"bombingmailto",                                   # Wortliste in Pillow/HarfBuzz
    r"@gmail\.com|_AT_gmail_DOT_com",                   # nur Domain: lokaler Teil wird weiter geprüft
    r"/home/(?:guido|user)\b",                         # Docstring-Beispiele in numpy
    r"Felix Hanau",                                     # Fremd-Autor in Qt-Lizenzhinweisen
    r"Email domain:\s+gmail\.com",                      # Qt-Lizenzhinweis, nur Domain
]))
# Anzeigename des Maintainers in Commits, die GitHub selbst erstellt (Squash-Merge im Web);
# ist ohnehin öffentlich im GitHub-Profil. Nur zusammen mit seiner noreply-Adresse ausgenommen.
OWNER_MAIL = "+felix-d-git@users.noreply.github.com"


def patterns(artifact=False):
    pats = [p for p in GENERIC if p != MAIL] if artifact else list(GENERIC)
    if artifact:
        pats[pats.index(KEY)] = KEY + r"\s*[A-Za-z0-9+/=]{40}"
    if LOCAL.exists():
        pats += [l.strip() for l in LOCAL.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
    else:
        print(f"WARNUNG: {LOCAL.name} fehlt — nur generische Muster aktiv.")
    return re.compile("|".join(f"(?:{p.removeprefix('(?i)')})" for p in pats), re.IGNORECASE)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def scan(label, text, rx, hits):
    for n, line in enumerate(text.splitlines(), 1):
        m = rx.search(line)
        if m:
            hits.append(f"{label}:{n}: [{m.group(0)}]")


def is_binary(name, data):
    return Path(name).suffix.lower() in SKIP_SUFFIX or b"\0" in data[:4096]


def check_text(label, data, rx, hits):
    scan(label, label, rx, hits)  # Dateiname selbst
    if not is_binary(label, data):
        scan(label, data.decode("utf-8", "replace"), rx, hits)
    else:
        # Binärdateien: nur eingebettete ASCII-Strings (z.B. Pfade in .exe/.pyc)
        for s in re.findall(rb"[\x20-\x7e]{8,}", data):
            m = rx.search(s.decode("ascii"))
            if m:
                hits.append(f"{label} (binär): [{m.group(0)}]")


def pyinstaller_members(path):
    """Inhalt der in eine PyInstaller-.exe angehängten Archive (CArchive + zlib-PYZ), entpackt."""
    try:
        from PyInstaller.archive.readers import CArchiveReader, NotAnArchiveError
    except ImportError:
        sys.exit(f"FEHLER: PyInstaller fehlt — {path} kann nicht entpackt geprüft werden.")
    if CArchiveReader._COOKIE_MAGIC_PATTERN not in path.read_bytes():
        return  # normale .exe ohne PyInstaller-Archiv
    pkg = CArchiveReader(str(path))  # defektes Archiv → Exception, kein stilles Durchwinken
    for name, entry in pkg.toc.items():
        if entry[-1] == "z":
            pyz = pkg.open_embedded_archive(name)
            for mod in pyz.toc:
                yield f"{name}/{mod}", pyz.extract(mod, raw=True)
        else:
            try:
                yield name, pkg.extract(name)
            except NotAnArchiveError:
                pass


def check_artifact(label, data, rx, hits):
    scan(label, label, rx, hits)
    if not data:  # z.B. Namespace-Pakete im PYZ
        return
    if data[:4] == b"PK\x03\x04":  # eingebettete ZIPs (z.B. base_library.zip) entpackt prüfen
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                check_artifact(f"{label}!{n}", z.read(n), rx, hits)
    texts = ([data.decode("utf-8", "replace")] if not is_binary(label, data)
             else [s.decode("ascii") for s in re.findall(rb"[\x20-\x7e\t\r\n]{8,}", data)])
    found = set()
    for t in texts:
        allowed = [m.span() for m in ARTIFACT_ALLOW.finditer(t)]
        # Treffer nur ignorieren, wenn er ganz in einem erlaubten Fremd-String liegt
        found |= {m.group(0) for m in rx.finditer(t)
                  if not any(a <= m.start() and m.end() <= b for a, b in allowed)}
    hits += [f"{label}: [{f}]" for f in sorted(found)]


def check_path(label, data, rx, hits, on_disk=None):
    check_artifact(label, data, rx, hits)
    if label.lower().endswith(".exe"):
        if on_disk is None:  # .exe im ZIP: zum Entpacken temporär auf Platte
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                (p := Path(d) / "a.exe").write_bytes(data)
                for n, b in pyinstaller_members(p):
                    check_artifact(f"{label}>{n}", b, rx, hits)
        else:
            for n, b in pyinstaller_members(on_disk):
                check_artifact(f"{label}>{n}", b, rx, hits)


def main():
    rx = patterns()
    rx_art = patterns(artifact=True)
    hits = []
    self_name = "scripts/check_privacy.py"

    def check_file(label, data, path=None):
        if (path or label).startswith(THIRD_PARTY_TEXTS):
            check_artifact(label, data, rx_art, hits)  # Fremdtexte: Artefakt-Regeln inkl. ARTIFACT_ALLOW
        else:
            check_text(label, data, rx, hits)

    # 1. Arbeitsstand (getrackt + gestagt)
    files = set(git("ls-files", "-z").decode().split("\0")) | set(
        git("diff", "--cached", "--name-only", "-z").decode().split("\0"))
    for f in sorted(x for x in files if x and x != self_name):
        p = ROOT / f
        if p.is_file():
            check_file(f, p.read_bytes())

    # 2. History: alle Blobs aller Commits, Messages, Identitäten
    if git("rev-list", "--all").strip():
        for line in git("rev-list", "--all", "--objects").decode().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[1] != self_name:
                if git("cat-file", "-t", parts[0]).strip() == b"blob":
                    check_file(f"history:{parts[1]}", git("cat-file", "-p", parts[0]), parts[1])
        log = git("log", "--all", "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x1e").decode()
        for entry in filter(str.strip, log.split("\x1e")):
            h, an, ae, cn, ce, body = entry.strip().split("\0", 5)
            for mail in (ae, ce):
                if not ALLOWED_AUTHOR.search(mail):
                    hits.append(f"commit {h[:8]}: Mail nicht noreply: {mail}")
            names = [n for n, m in ((an, ae), (cn, ce)) if not m.endswith(OWNER_MAIL)]
            scan(f"commit {h[:8]} meta", "\n".join(names + [body]), rx, hits)

    # 3. Zusätzliche Pfade (Build-Ordner, Release-ZIP)
    for extra in sys.argv[sys.argv.index("--extra") + 1:] if "--extra" in sys.argv else []:
        p = Path(extra)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    check_path(str(f.relative_to(p.parent)), f.read_bytes(), rx_art, hits, on_disk=f)
        elif p.suffix == ".zip":
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    check_path(f"{p.name}!{n}", z.read(n), rx_art, hits)
        elif p.is_file():  # weitere Release-Dateien (SBOM: purls wie pkg:pypi/x@1.0 sind keine Mails)
            check_path(p.name, p.read_bytes(), rx_art, hits, on_disk=p)
        else:
            sys.exit(f"FEHLER: --extra {extra} fehlt.")

    if hits:
        print("DATENSCHUTZ-CHECK FEHLGESCHLAGEN:")
        print("\n".join(hits[:200]))
        sys.exit(1)
    print("Datenschutz-Check OK")


if __name__ == "__main__":
    main()
