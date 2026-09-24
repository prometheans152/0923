"""Unit and integration tests for SQLite persistence and Flask SQLite API.

Gate 2: SQLite persistence with verifiable query output.
Gate 3: Flask API backed by SQLite.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import (
    connect_readonly,
    init_db,
    latest_observation_time,
    payload_from_db,
    query_sample,
    row_count,
    upsert_payload,
)
from server import app


def make_payload(obs_time: str, temperature: float = 25.0):
    station = {
        "station_id": "C0TEST",
        "station_name": "測試站",
        "county": "新竹縣",
        "town": "竹北市",
        "lat": 24.83,
        "lon": 121.01,
        "altitude": 20.0,
        "obs_time": obs_time,
        "weather": "晴",
        "temperature": temperature,
        "humidity": 65.0,
        "pressure": 1008.0,
        "wind_speed": 2.0,
        "wind_direction": 180.0,
        "gust_speed": 4.0,
        "precipitation": 0.0,
        "uv_index": 3.0,
        "color": "#F97316",
        "category": "溫暖",
        "has_temp": True,
    }
    return {
        "metadata": {
            "source": "CWA O-A0003-001",
            "generated_at": obs_time,
            "observation_time": obs_time,
            "total_stations": 1,
            "valid_temp_stations": 1,
            "stats": {
                "max_temperature": {"value": temperature, "station_name": "測試站", "county": "新竹縣"},
                "min_temperature": {"value": temperature, "station_name": "測試站", "county": "新竹縣"},
                "avg_temperature": temperature,
                "max_wind_speed": {"value": 2.0, "station_name": "測試站"},
                "max_precipitation": {"value": 0.0, "station_name": "測試站"},
            },
            "counties": ["新竹縣"],
            "color_scale": [],
            "build_mode": "test",
        },
        "stations": [station],
    }


def test_schema_initializes(tmp_path):
    """Verify tables observations, metadata, and snapshots are created."""
    db = tmp_path / "weather.db"
    init_db(db)
    assert db.is_file()
    assert row_count(db) == 0

    with connect_readonly(db) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "observations" in tables
        assert "metadata" in tables
        assert "snapshots" in tables

        # Verify required columns in observations
        cols = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(observations)").fetchall()
        }
        required = [
            "station_id", "station_name", "county", "town", "lat", "lon",
            "altitude", "obs_time", "weather", "temperature", "humidity",
            "pressure", "wind_speed", "wind_direction", "gust_speed",
            "precipitation", "uv_index", "color", "category", "has_temp"
        ]
        for c in required:
            assert c in cols, f"Missing required column {c} in observations"


def test_metadata_table_fields(tmp_path):
    """Verify metadata table stores required summary fields."""
    db = tmp_path / "weather.db"
    payload = make_payload("2026-09-24T17:00:00+08:00", 25.5)
    upsert_payload(db, payload, source_mode="test_mode")

    with connect_readonly(db) as conn:
        row = conn.execute("SELECT * FROM metadata WHERE id = 1").fetchone()
        assert row is not None
        assert row["source"] == "CWA O-A0003-001"
        assert row["observation_time"] == "2026-09-24T17:00:00+08:00"
        assert row["total_stations"] == 1
        assert row["valid_temp_stations"] == 1
        assert row["build_mode"] == "test_mode"


def test_atomic_snapshot_replacement(tmp_path):
    """Verify rebuilding replaces the snapshot atomically without orphan rows."""
    db = tmp_path / "weather.db"
    upsert_payload(db, make_payload("2026-09-24T10:00:00+08:00", 25.0), "test")
    assert row_count(db) == 1

    # Replace with updated observation
    upsert_payload(db, make_payload("2026-09-24T10:10:00+08:00", 26.5), "test")
    assert row_count(db) == 1
    assert latest_observation_time(db) == "2026-09-24T10:10:00+08:00"

    payload = payload_from_db(db)
    assert payload["stations"][0]["temperature"] == 26.5


def test_upsert_duplicate_station_behavior(tmp_path):
    """Verify upsert handles duplicate station_id gracefully without duplicates."""
    db = tmp_path / "weather.db"
    base_payload = make_payload("2026-09-24T10:00:00+08:00", 22.0)
    # Add a duplicate station entry with same station_id but updated temperature
    duplicate_station = dict(base_payload["stations"][0])
    duplicate_station["temperature"] = 29.5
    duplicate_station["weather"] = "多雲"
    payload_with_dupes = {
        "metadata": base_payload["metadata"],
        "stations": [base_payload["stations"][0], duplicate_station],
    }

    inserted = upsert_payload(db, payload_with_dupes, "test_upsert")
    assert inserted == 2  # Processed 2 entries
    assert row_count(db) == 1  # Exactly 1 row because station_id is PRIMARY KEY

    with connect_readonly(db) as conn:
        row = conn.execute(
            "SELECT temperature, weather FROM observations WHERE station_id = ?",
            ("C0TEST",),
        ).fetchone()
        assert row is not None
        # Last inserted duplicate overwrote the earlier record
        assert row["temperature"] == 29.5
        assert row["weather"] == "多雲"

    # Test incremental upsert with replace=False
    new_station = dict(base_payload["stations"][0])
    new_station["station_id"] = "C0SECOND"
    new_station["station_name"] = "第二測站"
    new_station["temperature"] = 21.0
    incremental_payload = {
        "metadata": base_payload["metadata"],
        "stations": [new_station],
    }
    upsert_payload(db, incremental_payload, "test_upsert", replace=False)
    assert row_count(db) == 2  # Now 2 unique stations

    # Update C0TEST again with replace=False
    update_station = dict(duplicate_station)
    update_station["temperature"] = 31.0
    update_payload = {
        "metadata": base_payload["metadata"],
        "stations": [update_station],
    }
    upsert_payload(db, update_payload, "test_upsert", replace=False)
    assert row_count(db) == 2  # Still 2 unique stations (no duplicates)
    with connect_readonly(db) as conn:
        row = conn.execute(
            "SELECT temperature FROM observations WHERE station_id = ?",
            ("C0TEST",),
        ).fetchone()
        assert row["temperature"] == 31.0


def test_row_count_matches_json():
    """Verify data.db station count exactly matches docs/data/stations.json."""
    db_path = PROJECT_ROOT / "data.db"
    json_path = PROJECT_ROOT / "docs" / "data" / "stations.json"

    assert db_path.is_file(), "data.db does not exist"
    assert json_path.is_file(), "stations.json does not exist"

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    json_stations = data.get("stations", [])
    total_in_meta = data.get("metadata", {}).get("total_stations", 0)

    db_count = row_count(db_path)
    assert db_count > 0, "Database is empty"
    assert db_count == len(json_stations), f"DB count {db_count} != JSON count {len(json_stations)}"
    assert db_count == total_in_meta, f"DB count {db_count} != metadata count {total_in_meta}"


def test_query_sample_works():
    """Verify query_sample returns properly formatted rows."""
    db_path = PROJECT_ROOT / "data.db"
    rows = query_sample(db_path, county="新竹縣", limit=3)
    assert len(rows) > 0, "Expected at least 1 sample row for 新竹縣"
    sample = rows[0]
    assert "station_name" in sample
    assert "county" in sample
    assert sample["county"] == "新竹縣"
    assert "temperature" in sample
    assert "humidity" in sample
    assert "obs_time" in sample


def test_latest_payload_reconstruction(tmp_path):
    """Verify payload_from_db reconstructs standard frontend contract."""
    db = tmp_path / "weather.db"
    upsert_payload(db, make_payload("2026-09-24T10:10:00+08:00", 26.0), "test")
    payload = payload_from_db(db)
    assert payload["metadata"]["storage"] == "sqlite"
    assert payload["metadata"]["total_stations"] == 1
    assert payload["metadata"]["observation_time"] == "2026-09-24T10:10:00+08:00"
    assert payload["stations"][0]["temperature"] == 26.0


def test_flask_api_weather_uses_sqlite():
    """Verify Flask /api/weather serves data from SQLite and matches DB count."""
    client = app.test_client()
    resp = client.get("/api/weather")
    assert resp.status_code == 200
    assert resp.is_json

    data = resp.get_json()
    assert "metadata" in data
    assert "stations" in data
    assert data["metadata"].get("storage") == "sqlite"

    db_path = PROJECT_ROOT / "data.db"
    db_count = row_count(db_path)
    assert len(data["stations"]) == db_count, (
        f"API returned {len(data['stations'])} stations, expected {db_count}"
    )


def test_flask_routes_all_200():
    """Verify all primary static and API routes return HTTP 200."""
    client = app.test_client()
    routes = [
        "/",
        "/app.js",
        "/data/stations.json",
        "/api/weather",
        "/api/db-check",
    ]
    for route in routes:
        resp = client.get(route)
        assert resp.status_code == 200, f"Route {route} returned status {resp.status_code}"
