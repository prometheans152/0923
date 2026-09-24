"""Verification script to test all requirements for Gates 1-5 locally."""
from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import query_sample, row_count
from server import app


def run_checks() -> None:
    db_p = PROJECT_ROOT / "data.db"
    assert db_p.is_file(), "data.db not found"
    db_cnt = row_count(db_p)
    print(f"[CHECK 1] SQLite row_count: {db_cnt} (count > 0: {db_cnt > 0})")
    assert db_cnt > 0

    json_p = PROJECT_ROOT / "docs" / "data" / "stations.json"
    assert json_p.is_file(), "stations.json not found"
    with json_p.open("r", encoding="utf-8") as f:
        json_data = json.load(f)

    json_cnt = len(json_data["stations"])
    meta_cnt = json_data["metadata"]["total_stations"]
    print(f"[CHECK 2] JSON stations count: {json_cnt}, metadata total: {meta_cnt}")
    print(f"[CHECK 3] JSON and DB counts match: {db_cnt == json_cnt == meta_cnt}")
    assert db_cnt == json_cnt == meta_cnt

    client = app.test_client()
    for route in ["/", "/app.js", "/data/stations.json", "/api/weather", "/api/db-check"]:
        res = client.get(route)
        print(f"[CHECK 4] Flask GET {route:22s} -> HTTP {res.status_code}")
        assert res.status_code == 200

    api_payload = client.get("/api/weather").get_json()
    api_cnt = len(api_payload.get("stations", []))
    storage = api_payload.get("metadata", {}).get("storage")
    build_mode = api_payload.get("metadata", {}).get("build_mode")
    obs_time = api_payload.get("metadata", {}).get("observation_time")
    print(f"[CHECK 5] /api/weather payload stations: {api_cnt}, storage: {storage}, mode: {build_mode}")
    print(f"[CHECK 6] /api/weather count matches SQLite DB: {api_cnt == db_cnt}")
    assert api_cnt == db_cnt
    assert storage == "sqlite"

    samples = query_sample(db_p, county="新竹縣", limit=3)
    print(f"[CHECK 7] SQLite query sample (新竹縣, {len(samples)} rows, observation_time={obs_time}):")
    for s in samples:
        print(f"          - {s['station_name']} ({s['station_id']}): {s['temperature']}°C, RH {s['humidity']}%, Weather: {s['weather']}")

    print("\n[ALL LOCAL VERIFICATION CHECKS PASSED]")


if __name__ == "__main__":
    run_checks()
