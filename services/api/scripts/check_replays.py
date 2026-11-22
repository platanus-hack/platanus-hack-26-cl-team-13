#!/usr/bin/env python3
"""Revisa que las grabaciones de apps/web/public/replays/ no contengan secretos verdaderos (pool B).

Con DATABASE_URL (la Postgres donde corrió la grabación): toma los valores verdaderos de cada
corrida con `store.secrets_for_run` y los busca con `scanner.find` (claro, base64, hex, url y
fragmentos de 16). Si encuentra alguno, falla (exit 1). Este es el check que vale.

Sin DATABASE_URL: solo busca prefijos inequívocos de los generadores (sk_live_, AKIA, ghp_,
sk-ant-api03-, sk-proj-, xoxb-). Los pools A (honeytokens) y B usan los mismos generadores, así
que no distingue un honeytoken, que es justo lo que la demo quiere mostrar, de un secreto
verdadero: solo AVISA y pide repetir con DATABASE_URL antes de publicar.

    cd services/api && DATABASE_URL=postgresql://... uv run python scripts/check_replays.py [archivos...]
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "api"))

from aigis import scanner  # noqa: E402

REPLAYS = ROOT / "apps" / "web" / "public" / "replays"
PREFIXES = re.compile(
    r"sk_live_[A-Za-z0-9]{24}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36}|sk-ant-api03-[A-Za-z0-9_-]{20,}"
    r"|sk-proj-[A-Za-z0-9]{48}|xoxb-\d{12}-\d{12}-[A-Za-z0-9]{24}"
)


def recordings(args: list[str]) -> list[Path]:
    if args:
        return [Path(a) for a in args]
    return sorted(p for p in REPLAYS.glob("*.json") if p.name != "index.json")


async def check_against(files: list[Path], store) -> int:
    """Busca en cada grabación los valores del pool B de su corrida. 1 si alguno aparece."""
    bad = 0
    for f in files:
        text = f.read_text("utf-8")
        run_id = json.loads(text)["run"]["id"]
        refs = [s for s in await store.secrets_for_run(run_id) if s.pool == "B"]
        if not refs:
            print(f"AVISO {f.name}: la base no tiene secretos de {run_id}; ¿es la base correcta?")
            continue
        hits = scanner.find(text, [(s.id, s.value) for s in refs], fragment_min=16)
        if hits:
            bad += 1
            kinds = sorted({f"{h.secret_id}:{h.encoding}" for h in hits})
            print(f"FALLA {f.name}: contiene secretos del pool B ({', '.join(kinds)})")
        else:
            print(f"ok    {f.name}: {len(refs)} secretos del pool B revisados, ninguno aparece")
    return 1 if bad else 0


async def check_with_db(files: list[Path], dsn: str) -> int:
    from aigis.store_pg import PostgresStore

    st = PostgresStore(dsn, max_size=2)
    await st.open()
    try:
        return await check_against(files, st)
    finally:
        await st.close()


def check_without_db(files: list[Path]) -> int:
    print("Sin DATABASE_URL: solo se buscan prefijos y no se distingue honeytoken de secreto verdadero.\n")
    flagged = 0
    for f in files:
        found = sorted(set(PREFIXES.findall(f.read_text("utf-8"))))
        if found:
            flagged += 1
            shown = ", ".join(v[:10] + "…" for v in found[:5])
            print(f"AVISO {f.name}: {len(found)} valores con formato de llave ({shown})")
        else:
            print(f"ok    {f.name}: sin valores con formato de llave")
    if flagged:
        print("\nRepite con DATABASE_URL de la base de la grabación antes de publicar.")
    return 0


def main() -> int:
    files = recordings(sys.argv[1:])
    if not files:
        print("no hay grabaciones")
        return 0
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("AIGIS_DATABASE_URL")
    return asyncio.run(check_with_db(files, dsn)) if dsn else check_without_db(files)


if __name__ == "__main__":
    raise SystemExit(main())
