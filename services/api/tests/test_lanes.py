"""Catálogo de carriles: none, monitor, fides y gemelo.

El flujo completo de los cuatro carriles contra un ataque está en test_run_flow.py.
Aquí se verifica el catálogo, los flags y la política que recibe cada caja.
"""

from __future__ import annotations

import json

from aigis.agent import build_command
from aigis.config import Settings
from aigis.lanes.catalog import CATALOG, DEFAULT_LANES, get_spec

LANES = ["none", "monitor", "fides", "gemelo"]


def test_catalog_is_the_four_lanes():
    assert DEFAULT_LANES == LANES
    assert list(CATALOG) == LANES
    assert Settings().lane_list == LANES


def test_sota_lanes_have_sources_and_gaps():
    for lane in DEFAULT_LANES:
        spec = get_spec(lane)
        if spec.family == "estado_del_arte":
            assert spec.sources and all(s.evidence in "ABC" and s.date for s in spec.sources)
            assert spec.known_gaps


def test_all_lanes_skip_permissions():
    st = Settings(agent="claude")
    for lane in LANES:
        c = build_command(st, "x", twin=lane == "gemelo", script_path=None, permission_args=CATALOG[lane].cli)
        assert "--dangerously-skip-permissions" in c, lane


def test_lanes_endpoint(harness):
    with harness.client() as c:
        body = c.get("/lanes").json()
    assert [x["id"] for x in body["lanes"]] == LANES
    assert body["default"] == LANES


def test_removed_lanes_are_rejected(harness):
    with harness.client() as c:
        for lane in ("nope", "cc_sandbox", "auto_mode"):
            r = c.post("/runs", json={"task_id": "mask-keys", "lanes": [lane]})
            assert r.status_code == 422, lane


def test_managed_settings_written_per_box(harness):
    seen = {}
    orig = harness.provider.write_files

    async def spy(sb, files, mode=0o644, owner="agent"):
        for path, data in files.items():
            if path == "/etc/claude-code/managed-settings.json":
                seen[(sb.spec.lane, sb.spec.role)] = (json.loads(data), owner)
        await orig(sb, files, mode=mode, owner=owner)

    harness.provider.write_files = spy
    try:
        with harness.client() as c:
            run_id = c.post("/runs", json={"task_id": "mask-keys", "lanes": LANES}).json()["run_id"]
        harness.wait_run(run_id)
    finally:
        harness.provider.write_files = orig
    assert {lane for lane, _ in seen} == set(LANES)
    for (lane, role), (settings, owner) in seen.items():
        assert owner == "root", (lane, role)
        assert "hooks" in settings and "sandbox" not in settings and "permissions" not in settings
