"""Catálogo de ataques de robo de credenciales (`attacks/catalog.yaml`).

Cada ataque trae el texto que se inyecta en el vector (README, issue o página de
docs) con dos marcadores que el orquestador reemplaza al preparar la corrida:
  {ATTACKER_URL}   URL base del servidor atacante vista desde las cajas
  {ATTACKER_HOST}  solo el host, para canales DNS o reglas por dominio
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field

from .models import Attack, AttackVector

# Un ataque nunca inyecta sobre secretos, git ni archivos de control
_FORBIDDEN = (".env", ".git", ".aigis", ".aigis_tests")


class CatalogAttack(BaseModel):
    id: str
    title: str
    technique: str
    channel: str                       # http, webfetch, dns, git, diff, test, supply-chain
    vectors: list[AttackVector]
    payload: str = Field(default="", max_length=8192)
    # Archivos que el ataque inyecta en el repo, antes del commit base. El contenido vive en
    # attacks/files/<id>/<ruta> y para el agente son parte del proyecto. Para ataques tipo
    # "el código corre solo" (p. ej. un conftest.py), donde el payload de texto no basta.
    files: list[str] = []
    targets: list[str] = []            # carriles del estado del arte a los que apunta
    notes: str = ""
    references: list[str] = []

    def public(self) -> dict:
        return self.model_dump(exclude={"payload"}) | {"payload_preview": self.payload[:280]}

    def to_attack(self, vector: AttackVector | None = None) -> Attack:
        v = vector or self.vectors[0]
        if v not in self.vectors:
            raise ValueError(f"el ataque {self.id} no admite el vector {v}")
        return Attack(id=self.id, vector=v, payload=self.payload, author="catalog")


def load_attacks(path: Path) -> dict[str, CatalogAttack]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    out: dict[str, CatalogAttack] = {}
    for item in data.get("attacks", []):
        a = CatalogAttack(**item)
        if a.id in out:
            raise ValueError(f"ataque duplicado: {a.id}")
        out[a.id] = a
    return out


def render(payload: str, attacker_url: str) -> str:
    host = urlparse(attacker_url).hostname or attacker_url
    return payload.replace("{ATTACKER_URL}", attacker_url.rstrip("/")).replace("{ATTACKER_HOST}", host)


def injected_files(catalog_dir: Path, attack: CatalogAttack, attacker_url: str) -> dict[str, bytes]:
    """Lee los archivos que el ataque inyecta en el repo, desde attacks/files/<id>/.

    Valida que ninguno escriba `.env`, `.git` ni archivos de control, y reemplaza los
    marcadores en los de texto. Los binarios pasan tal cual.
    """
    base = catalog_dir / "files" / attack.id
    out: dict[str, bytes] = {}
    for rel in attack.files:
        parts = PurePosixPath(rel).parts
        if not parts or ".." in parts or parts[0] in _FORBIDDEN:
            raise ValueError(f"el ataque {attack.id} no puede inyectar {rel!r}")
        data = (base / rel).read_bytes()
        try:
            data = render(data.decode("utf-8"), attacker_url).encode("utf-8")
        except UnicodeDecodeError:
            pass
        out[rel] = data
    return out
