"""Datenschutz-Check: blockiert Commits/Pushes/Releases mit persönlichen Daten.

Prüft
  1. alle getrackten + gestagten Dateien (Inhalt + Pfad),
  2. die komplette Git-History (alle Blobs, Commit-Messages, Autor/Committer),
  3. optional Verzeichnisse/ZIPs (Build-Artefakte): --extra dist/ Kurvenwerk.zip

Muster = generische Regexe hier + private Begriffe aus `.privacy-patterns.txt`
(gitignored, eine Regex pro Zeile, # = Kommentar). Exit 1 bei Treffer.
"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".privacy-patterns.txt"

GENERIC = [
    r"[A-Za-z]:[\\/]+Users[\\/]+(?!runneradmin)",   # Windows-Nutzerpfade
    r"/home/[a-z]",                                 # Linux-Nutzerpfade
    r"[\w.+-]+@(?!users\.noreply\.github\.com|anthropic\.com|example\.(?:com|org))[\w-]+\.[\w.]+",  # E-Mails
    r"gh[pousr]_[A-Za-z0-9]{30,}",                  # GitHub-Token
    r"sk-[A-Za-z0-9_-]{20,}",                       # API-Keys
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)(password|passwort|secret|api_key|token)\s*[:=]\s*['\"][^'\"]{6,}",
]
ALLOWED_AUTHOR = re.compile(r"(@users\.noreply\.github\.com|noreply@anthropic\.com|noreply@github\.com)$")
SKIP_SUFFIX = {".png", ".ico", ".ttf", ".otf", ".woff", ".woff2", ".pdf", ".dll", ".pyd", ".exe", ".so"}


def patterns():
    pats = list(GENERIC)
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


def main():
    rx = patterns()
    hits = []
    self_name = "scripts/check_privacy.py"

    # 1. Arbeitsstand (getrackt + gestagt)
    files = set(git("ls-files", "-z").decode().split("\0")) | set(
        git("diff", "--cached", "--name-only", "-z").decode().split("\0"))
    for f in sorted(x for x in files if x and x != self_name):
        p = ROOT / f
        if p.is_file():
            check_text(f, p.read_bytes(), rx, hits)

    # 2. History: alle Blobs aller Commits, Messages, Identitäten
    if git("rev-list", "--all").strip():
        for line in git("rev-list", "--all", "--objects").decode().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[1] != self_name:
                if git("cat-file", "-t", parts[0]).strip() == b"blob":
                    check_text(f"history:{parts[1]}", git("cat-file", "-p", parts[0]), rx, hits)
        log = git("log", "--all", "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x1e").decode()
        for entry in filter(str.strip, log.split("\x1e")):
            h, an, ae, cn, ce, body = entry.strip().split("\0", 5)
            for mail in (ae, ce):
                if not ALLOWED_AUTHOR.search(mail):
                    hits.append(f"commit {h[:8]}: Mail nicht noreply: {mail}")
            scan(f"commit {h[:8]} meta", f"{an}\n{cn}\n{body}", rx, hits)

    # 3. Zusätzliche Pfade (Build-Ordner, Release-ZIP)
    for extra in sys.argv[sys.argv.index("--extra") + 1:] if "--extra" in sys.argv else []:
        p = Path(extra)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    check_text(str(f.relative_to(p.parent)), f.read_bytes(), rx, hits)
        elif p.suffix == ".zip":
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    check_text(f"{p.name}!{n}", z.read(n), rx, hits)

    if hits:
        print("DATENSCHUTZ-CHECK FEHLGESCHLAGEN:")
        print("\n".join(hits[:200]))
        sys.exit(1)
    print("Datenschutz-Check OK")


if __name__ == "__main__":
    main()
