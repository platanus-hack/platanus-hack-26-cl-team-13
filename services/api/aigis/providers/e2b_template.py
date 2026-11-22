"""Construye la plantilla E2B desde sandbox/Dockerfile (una sola etapa).

    cd services/api && E2B_API_KEY=... uv run python -m aigis.providers.e2b_template [--force]

El nombre es aigis-sandbox-<hash de sandbox/> (ver e2b.template_name). Si ya existe, no
hace nada: así sirve de pre-deploy en Render y solo construye cuando cambia sandbox/.
--force reconstruye igual (por ejemplo, para tomar una versión nueva de la imagen base).

La imagen local y la plantilla E2B salen del mismo archivo. E2B no admite Dockerfiles
multi-stage (docs.e2b.dev/template/base-image).
"""

from __future__ import annotations

import argparse
import os
import sys

from aigis.config import get_settings
from aigis.providers.e2b import template_name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Construye la plantilla E2B de este código si falta")
    ap.add_argument("--force", action="store_true", help="reconstruir aunque ya exista")
    args = ap.parse_args(argv)

    from e2b import Template

    if not os.environ.get("E2B_API_KEY"):
        print("falta E2B_API_KEY en el entorno", file=sys.stderr)
        return 2
    ctx = get_settings().sandbox_dir
    name = template_name(ctx)
    if not args.force and Template.exists(name):
        print(f"plantilla ya existe: {name}", flush=True)
        return 0
    print(f"construyendo plantilla {name} desde {ctx / 'Dockerfile'}", flush=True)
    tpl = Template(file_context_path=str(ctx)).from_dockerfile(str(ctx / "Dockerfile"))
    info = Template.build(tpl, name, cpu_count=2, memory_mb=2048,
                          on_build_logs=lambda e: print(getattr(e, "message", e), flush=True))
    print(f"plantilla lista: {name} {info}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
