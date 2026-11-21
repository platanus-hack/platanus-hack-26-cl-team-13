"""Construye la plantilla E2B desde sandbox/Dockerfile (una sola etapa).

    cd services/api && E2B_API_KEY=... uv run python -m gemelo.providers.e2b_template

La imagen local y la plantilla E2B salen del mismo archivo. E2B no admite Dockerfiles
multi-stage (docs.e2b.dev/template/base-image).
"""

from __future__ import annotations

import os
import sys

from gemelo.config import get_settings
from gemelo.providers.e2b import TEMPLATE


def main() -> int:
    from e2b import Template

    if not os.environ.get("E2B_API_KEY"):
        print("falta E2B_API_KEY en el entorno", file=sys.stderr)
        return 2
    ctx = get_settings().sandbox_dir
    tpl = Template(file_context_path=str(ctx)).from_dockerfile(str(ctx / "Dockerfile"))
    info = Template.build(tpl, alias=TEMPLATE, cpu_count=2, memory_mb=2048,
                          on_build_logs=lambda e: print(getattr(e, "message", e), flush=True))
    print(f"plantilla lista: {TEMPLATE} {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
