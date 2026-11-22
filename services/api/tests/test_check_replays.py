"""scripts/check_replays.py: falla si una grabación trae un secreto del pool B."""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json

from aigis.config import REPO_ROOT
from aigis.models import SecretRef
from aigis.store import MemoryStore

_spec = importlib.util.spec_from_file_location("check_replays", REPO_ROOT / "services/api/scripts/check_replays.py")
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)

REAL = "AKIA" + "Q7RZ" * 4
HONEY = "AKIA" + "H0NY" * 4


def _rec(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(json.dumps({"meta": {}, "run": {"id": "run_x"}, "events": [{"data": {"out": text}}], "diffs": {}}))
    return p


def _store() -> MemoryStore:
    st = MemoryStore()
    for sid, pool, value in (("b1", "B", REAL), ("a1", "A", HONEY)):
        asyncio.run(st.save_secret(SecretRef(id=sid, pool=pool, env_name="AWS_ACCESS_KEY_ID",
                                             kind="aws_access_key", value=value, run_id="run_x")))
    return st


def test_falla_con_secreto_verdadero_incluso_en_base64(tmp_path, capsys):
    st = _store()
    plain = _rec(tmp_path, "a.json", f"curl -d {REAL}")
    b64 = _rec(tmp_path, "b.json", base64.b64encode(REAL.encode()).decode())
    assert asyncio.run(cr.check_against([plain], st)) == 1
    assert asyncio.run(cr.check_against([b64], st)) == 1
    assert "FALLA" in capsys.readouterr().out


def test_honeytoken_no_falla(tmp_path):
    assert asyncio.run(cr.check_against([_rec(tmp_path, "c.json", f"llegó {HONEY}")], _store())) == 0


def test_sin_base_solo_avisa(tmp_path, capsys):
    assert cr.check_without_db([_rec(tmp_path, "d.json", f"x {HONEY} y")]) == 0
    assert "AVISO d.json" in capsys.readouterr().out
