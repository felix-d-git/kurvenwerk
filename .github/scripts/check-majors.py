#!/usr/bin/env python3
"""Zeigt verfügbare Major-Versionen und EOL-Stände eines Projekts (vor jeder Feature-Arbeit ausführen).

  python check-majors.py [projektpfad]

Prüft Basis-Images (Dockerfile*/compose) gegen endoflife.date sowie Pakete per
npm/composer/pip outdated. Nur Bericht, ändert nichts.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

# Image-Name -> endoflife.date-Produkt
PRODUCTS = {"node": "nodejs", "php": "php", "python": "python", "postgres": "postgresql", "redis": "redis",
            "nginx": "nginx", "mariadb": "mariadb", "mysql": "mysql", "alpine": "alpine", "debian": "debian",
            "ubuntu": "ubuntu", "golang": "go", "ruby": "ruby", "eclipse-temurin": "eclipse-temurin",
            "mongo": "mongodb", "rabbitmq": "rabbitmq", "traefik": "traefik", "caddy": "caddy"}
IMAGE = re.compile(r"^\s*(?:FROM\s+(?:--platform=\S+\s+)?|image:\s*)[\"']?(?:docker\.io/)?(?:library/)?"
                   r"([a-z0-9._-]+):([0-9][^\s\"'@]*)", re.I | re.M)
SKIP_DIRS = {"node_modules", ".git", "vendor", ".venv", "venv", "dist", "build", ".next", "graphify-out"}
TODAY = datetime.date.today().isoformat()


def ver(s, n=None):
    parts = [int(x) for x in re.findall(r"\d+", s)]
    return tuple(parts[:n] if n else parts)


def released(lts):
    return lts is True or (isinstance(lts, str) and lts <= TODAY)


def eol_data(product, cache={}):
    if product not in cache:
        try:
            with urllib.request.urlopen(f"https://endoflife.date/api/{product}.json", timeout=15) as r:
                cache[product] = json.load(r)
        except Exception as e:
            cache[product] = e
    return cache[product]


def check_images(root):
    out, seen = [], set()
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not (f.startswith("Dockerfile") or re.match(r"(docker-)?compose.*\.ya?ml$", f)):
                continue
            path = os.path.join(dirpath, f)
            for name, tag in IMAGE.findall(open(path, encoding="utf-8", errors="replace").read()):
                product = PRODUCTS.get(name.lower())
                if not product or (name, tag) in seen:
                    continue
                seen.add((name, tag))
                data = eol_data(product)
                if isinstance(data, Exception):
                    out.append(f"  ? {name}:{tag} – endoflife.date nicht erreichbar ({data})")
                    continue
                # Bei LTS-Produkten (node, ubuntu) die neueste bereits erschienene LTS, sonst den neuesten Zyklus.
                newest = next((c for c in data if released(c.get("lts"))), data[0]) \
                    if any("lts" in c and c["lts"] for c in data) else data[0]
                # python:3 nur auf Major vergleichen, python:3.12 auf Minor
                depth = min(len(ver(tag)), len(ver(newest["cycle"])))
                if not depth:
                    continue
                mine = next((c for c in data if ver(c["cycle"]) == ver(tag, depth)), None)
                rel = os.path.relpath(path, root)
                if mine and isinstance(mine.get("eol"), str) and mine["eol"] <= TODAY:
                    out.append(f"  ✖ {name}:{tag} ({rel}) ist EOL seit {mine['eol']} → {newest['cycle']}")
                elif ver(tag, depth) < ver(newest["cycle"], depth):
                    out.append(f"  ↑ {name}:{tag} ({rel}) → {newest['cycle']} verfügbar")
    return out


def run_json(cmd, cwd, kind):
    """Geparstes JSON vom Typ `kind`, sonst Fehlertext (str) – nie stilles OK."""
    name = os.path.basename(cmd[0])
    exe = shutil.which(cmd[0])
    if not exe:
        return f"{name} nicht gefunden"
    try:
        r = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120)
        data = json.loads(r.stdout or "null") or kind()
    except subprocess.TimeoutExpired:
        return f"{name} Timeout"
    except json.JSONDecodeError:
        return f"{name}: keine JSON-Ausgabe ({r.stderr.strip()[:100]})"
    if isinstance(data, dict) and "error" in data:
        return f"{name}: {str(data['error'])[:100]}"
    return data if isinstance(data, kind) else f"{name}: unerwartete Ausgabe"


def check_packages(root):
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(dirpath, root)
        if "package.json" in files:
            data = run_json(["npm", "outdated", "--json"], dirpath, dict)
            for pkg, i in data.items() if isinstance(data, dict) else []:
                i = i[0] if isinstance(i, list) else i  # Workspaces liefern Listen
                cur, latest = i.get("current") or i.get("wanted", "0"), i.get("latest", "0")
                if ver(cur, 1) < ver(latest, 1):
                    out.append(f"  ↑ npm {pkg} {cur} → {latest} ({rel})")
            out += [f"  ? npm ({rel}) nicht geprüft: {data}"] if isinstance(data, str) else []
        if "composer.json" in files:
            data = run_json(["composer", "outdated", "--direct", "--major-only", "--format=json"], dirpath, dict)
            for i in data.get("installed", []) if isinstance(data, dict) else []:
                out.append(f"  ↑ composer {i['name']} {i['version']} → {i['latest']} ({rel})")
            out += [f"  ? composer ({rel}) nicht geprüft: {data}"] if isinstance(data, str) else []
        if {"requirements.txt", "pyproject.toml"} & set(files):
            py = next((p for p in (os.path.join(dirpath, ".venv", "Scripts", "python.exe"),
                                   os.path.join(dirpath, ".venv", "bin", "python")) if os.path.exists(p)), None)
            data = run_json([py, "-m", "pip", "list", "--outdated", "--format=json"], dirpath, list) if py                 else "kein .venv"
            for i in data if isinstance(data, list) else []:
                if ver(i["version"], 1) < ver(i["latest_version"], 1):
                    out.append(f"  ↑ pip {i['name']} {i['version']} → {i['latest_version']} ({rel})")
            out += [f"  ? pip ({rel}) nicht geprüft: {data}"] if isinstance(data, str) else []
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:] == ["selftest"]:
        assert ver("17-alpine", 1) == (17,) and ver("3.12-slim", 2) == (3, 12) and ver("3.13") > ver("3.12-slim", 2)
        assert released(True) and released("2000-01-01") and not released(False) and not released("2999-01-01")
        assert IMAGE.findall("FROM node:22-alpine AS b\n  image: postgres:17-alpine\nFROM python:3.12") == \
            [("node", "22-alpine"), ("postgres", "17-alpine"), ("python", "3.12")]
        return print("selftest ok")
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    found = check_images(root) + check_packages(root)
    print(f"Major-Check {root}:")
    print("\n".join(found) if found else "  alles auf aktuellem Major")


if __name__ == "__main__":
    main()
