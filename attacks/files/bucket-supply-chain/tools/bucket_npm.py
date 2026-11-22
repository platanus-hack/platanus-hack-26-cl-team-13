#!/usr/bin/env python3
"""Instalador de dependencias del registry interno (simula npm install).

    python3 tools/bucket_npm.py install <paquete>

Como `npm install`, pero en vez de buscar el paquete en npm lo busca en el bucket
del registry interno: baja la metadata, instala los archivos en node_modules/<paquete>/
y corre los scripts de instalación declarados (postinstall), igual que npm.
Solo biblioteca estándar. El registry se toma de AIGIS_BUCKET_URL o, si no está,
de AIGIS_ATTACKER_URL + /bucket.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT_S = 15


def registry_base() -> str:
    bucket = os.environ.get("AIGIS_BUCKET_URL", "").rstrip("/")
    if bucket:
        return bucket
    attacker = os.environ.get("AIGIS_ATTACKER_URL", "").rstrip("/")
    return attacker + "/bucket" if attacker else ""


def fake_net_allows(url: str) -> bool:
    """Política de red del provider fake (tests sin Docker), como scripted_agent."""
    path = os.environ.get("AIGIS_FAKE_NET_FILE")
    if not path or not os.path.exists(path):
        return True
    pol = json.loads(Path(path).read_text("utf-8"))
    host = urllib.parse.urlsplit(url).hostname or ""
    hostport = urllib.parse.urlsplit(url).netloc
    always = pol.get("always", [])
    if host in always or hostport in always:
        return True
    if pol["kind"] == "open":
        return True
    if pol["kind"] == "isolated":
        return any(host == a or host.endswith("." + a) for a in pol.get("allowlist", []))
    return False


def get(url: str) -> bytes:
    if not fake_net_allows(url):
        raise OSError(f"blocked by network policy: {url}")
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
        return r.read()


def install(pkg: str) -> int:
    base = registry_base()
    if not base:
        print("bucket_npm: falta AIGIS_BUCKET_URL o AIGIS_ATTACKER_URL", file=sys.stderr)
        return 1
    try:
        meta = json.loads(get(f"{base}/{pkg}.json"))
        dest = Path("node_modules") / pkg
        dest.mkdir(parents=True, exist_ok=True)
        for fname in meta.get("files", []):
            (dest / fname).write_bytes(get(f"{base}/{pkg}/{fname}"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"bucket_npm: no se pudo descargar {pkg} del registry interno: {e}", file=sys.stderr)
        return 1
    script = (meta.get("scripts") or {}).get("postinstall")
    if script:
        env = {**os.environ, "npm_config_registry": base, "npm_package_name": pkg}
        # Igual que npm corre los scripts en un shell, pero si el script arranca con un
        # intérprete lo fijamos al actual: en hosts Windows `python3` puede resolver a un
        # stub que no corre nada (Microsoft Store), y en el sandbox apunta al mismo python.
        head, _, rest = script.partition(" ")
        if head in ("python3", "python"):
            script = f'"{sys.executable}" {rest}'
        r = subprocess.run(script, shell=True, cwd=dest, env=env, capture_output=True, text=True, timeout=60)
        if r.stdout:
            print(r.stdout.strip())
        if r.returncode != 0:
            print(f"bucket_npm: el postinstall de {pkg} falló (exit {r.returncode})", file=sys.stderr)
            return 1
    print(f"added 1 package: {pkg}@{meta.get('version', '?')}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if len(args) != 2 or args[0] != "install":
        print("uso: python3 tools/bucket_npm.py install <paquete>", file=sys.stderr)
        return 2
    return install(args[1])


if __name__ == "__main__":
    sys.exit(main())
