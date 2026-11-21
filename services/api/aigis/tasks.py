"""Carga de tareas desde `tasks/<id>/`.

Estructura (ver tasks/README.md):
  task.yaml         definición
  repo/             repo sobre el que trabaja el agente
  tests/            tests de la tarea; se copian a la caja recién al terminar el agente
  secrets.template  NOMBRE=tipo por secreto, sin valores
  issue_template.md opcional, con {payload}
  doc_page.md       opcional, página de docs para el vector webpage, con {payload}
  scripts/*.json    guiones del agente con guion
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from .honeytokens import parse_template
from .models import AttackVector


class Task(BaseModel):
    id: str
    title: str
    prompt: str
    test_cmd: list[str] = ["python3", "-m", "pytest", "-q", ".aigis_tests"]
    allowlist: list[str] = []
    vectors: list[AttackVector] = ["readme", "issue", "webpage"]
    doc_path: str = "/docs/index.html"
    dir: Path

    @property
    def repo_dir(self) -> Path:
        return self.dir / "repo"

    @property
    def tests_dir(self) -> Path:
        return self.dir / "tests"

    def secret_spec(self) -> list[tuple[str, str]]:
        p = self.dir / "secrets.template"
        return parse_template(p.read_text("utf-8")) if p.exists() else []

    def issue_template(self) -> str:
        p = self.dir / "issue_template.md"
        return p.read_text("utf-8") if p.exists() else "# Issue\n\n{payload}\n"

    def doc_page(self) -> str:
        p = self.dir / "doc_page.md"
        return p.read_text("utf-8") if p.exists() else "<html><body><h1>Docs</h1><p>{payload}</p></body></html>"

    def script(self, name: str) -> Path | None:
        p = self.dir / "scripts" / f"{name}.json"
        return p if p.exists() else None

    def public(self) -> dict:
        return {"id": self.id, "title": self.title, "vectors": self.vectors}


def load_tasks(tasks_dir: Path) -> dict[str, Task]:
    out: dict[str, Task] = {}
    if not tasks_dir.exists():
        return out
    for d in sorted(tasks_dir.iterdir()):
        y = d / "task.yaml"
        if d.is_dir() and y.exists():
            data = yaml.safe_load(y.read_text("utf-8")) or {}
            data.setdefault("id", d.name)
            out[data["id"]] = Task(dir=d, **data)
    return out


def iter_files(root: Path) -> list[tuple[str, bytes]]:
    """Archivos bajo `root` con ruta relativa en formato posix, sin __pycache__."""
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            files.append((p.relative_to(root).as_posix(), p.read_bytes()))
    return files
