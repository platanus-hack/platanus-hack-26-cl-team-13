"""Tests de regresiÃ³n del cÃ³digo exfiltrador de los ataques kind=code.

Cada archivo inyectable en el repo debe: compilar, no imprimir nada raro y mandar el
contenido de .env al sink del atacante cuando se dispara por su mecanismo:
  - conftest.py          -> al importarlo (recolecciÃ³n de pytest)
  - sitecustomize.py     -> al arrancar cualquier intÃ©rprete con el repo en sys.path
  - app/__init__.py      -> al importar el paquete de la tarea
  - tools/check_format.py-> al correrlo como script (sale 0 y reporta formato)

Corren contra un sink HTTP local: la prueba es conductual, no de plomerÃ­a.
"""

from __future__ import annotations

import http.server
import socket
import subprocess
import sys
import threading
import tempfile
from pathlib import Path

import pytest

from aigis.attacks import injected_files, load_attacks
from aigis.config import REPO_ROOT

CATALOG_DIR = REPO_ROOT / "attacks"
FILES_DIR = CATALOG_DIR / "files"
ENV_BODY = "STRIPE_API_KEY=sk_test_regresion_1234567890\n"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Sink(http.server.BaseHTTPRequestHandler):
    bodies: list[bytes] = []

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        type(self).bodies.append(self.rfile.read(n))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


@pytest.fixture
def sink(tmp_path):
    port = _free_port()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Sink)
    _Sink.bodies.clear()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def _inject(attack_id: str, tmp_path: Path, attacker_url: str) -> Path:
    """Repo mÃ­nimo con los archivos del ataque y un .env sintÃ©tico."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text(ENV_BODY, "utf-8")
    files = injected_files(CATALOG_DIR, load_attacks(CATALOG_DIR / "catalog.yaml")[attack_id], attacker_url)
    for rel, data in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return repo


def _run(repo: Path, argv: list[str], attacker_url: str, *, cwd: Path | None = None,
         env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {"AIGIS_ATTACKER_URL": attacker_url, "AIGIS_ENV_PATH": str(repo / ".env"),
           "PYTHONIOENCODING": "utf-8", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
           "PATH": __import__("os").environ.get("PATH", "")}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, *argv], cwd=str(cwd or repo), env=env,
                          capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("mech,argv", [
    ("conftest", ["-c", "import conftest"]),
    ("sitecustomize", ["-c", "pass"]),
    ("app", ["-c", "import app"]),
])
def test_repo_conftest_exfiltrates(sink, tmp_path, mech, argv):
    repo = _inject("repo-conftest", tmp_path, sink)
    env_extra = {"PYTHONPATH": str(repo)} if mech == "sitecustomize" else {}
    r = _run(repo, argv, sink, env_extra=env_extra)
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert b"sk_test_regresion_1234567890" in b"".join(_Sink.bodies), f"{mech}: no exfiltrÃ³"


def test_docs_checker_exfiltrates_and_passes(sink, tmp_path):
    repo = _inject("docs-checker", tmp_path, sink)
    (repo / "app").mkdir()
    (repo / "app" / "x.py").write_text("x = 1\n", "utf-8")
    r = _run(repo, ["tools/check_format.py"], sink)
    assert r.returncode == 0, r.stderr
    assert "format: OK" in r.stdout, r.stdout
    assert "Traceback" not in r.stderr, r.stderr
    assert b"sk_test_regresion_1234567890" in b"".join(_Sink.bodies)


def test_injected_files_compile():
    for aid, attack in load_attacks(CATALOG_DIR / "catalog.yaml").items():
        for rel, data in injected_files(CATALOG_DIR, attack, "http://attacker.test").items():
            if rel.endswith(".py"):
                compile(data.decode("utf-8"), f"{aid}/{rel}", "exec")


def test_attacker_url_placeholder_resolved():
    """Sin AIGIS_ATTACKER_URL, el marcador {ATTACKER_URL} queda resuelto por render()."""
    files = injected_files(CATALOG_DIR, load_attacks(CATALOG_DIR / "catalog.yaml")["repo-conftest"],
                           "http://attacker.test:9000")
    src = files["conftest.py"].decode("utf-8")
    assert "{ATTACKER_URL}" not in src and "http://attacker.test:9000" in src

