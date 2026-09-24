"""Focused tests for CWA temperature forecast data pipeline and API.

Verifies:
1. SQLite schema: TemperatureForecasts table with exact column names and UNIQUE constraint.
2. Normalization:
   - Compatibility with legacy course F-A0010-001 format (F-A0010-001 reference).
   - Current official F-C0032-003 7-day forecast format with MaxT/MinT extraction.
3. 6 course regions: 北部地區, 中部地區, 南部地區, 東北部地區, 東部地區, 東南部地區.
4. Database helpers: upsert/replace, list regions, query rows, reconstruct payload.
5. Live integration: docs/data/forecast.json and data.db with current 7-day span and F-C0032-003 metadata.
6. Flask API: /api/forecast and /api/forecast?region=...
7. Observation data preservation during build.
8. Honest error/fallback reporting.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import (
    COURSE_REGIONS,
    connect_readonly,
    forecast_payload_from_db,
    forecast_row_count,
    init_db,
    list_forecast_regions,
    query_forecast_rows,
    row_count,
    upsert_forecast_payload,
    upsert_forecast_rows,
    upsert_payload,
)
from fetch_and_build import build_dataset, build_forecast_dataset
from normalize import normalize_forecast_dataset
from server import app

EXPECTED_COURSE_REGIONS = [
    "北部地區",
    "中部地區",
    "南部地區",
    "東北部地區",
    "東部地區",
    "東南部地區",
]


def test_temperature_forecasts_table_schema(tmp_path):
    """Verify TemperatureForecasts table is created with exact columns and UNIQUE constraint."""
    db_file = tmp_path / "test_schema.db"
    init_db(db_file)

    with connect_readonly(db_file) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "TemperatureForecasts" in tables

        col_info = conn.execute("PRAGMA table_info(TemperatureForecasts)").fetchall()
        cols = {r["name"]: r["type"].upper() for r in col_info}

        assert "id" in cols
        assert "INTEGER" in cols["id"]
        assert "regionName" in cols
        assert cols["regionName"] == "TEXT"
        assert "dataDate" in cols
        assert cols["dataDate"] == "TEXT"
        assert "mint" in cols
        assert cols["mint"] == "REAL"
        assert "maxt" in cols
        assert cols["maxt"] == "REAL"

        # Verify not null constraints
        notnulls = {r["name"]: bool(r["notnull"]) for r in col_info}
        assert notnulls["regionName"] is True
        assert notnulls["dataDate"] is True


def test_normalize_forecast_dataset_legacy_fa0010_001():
    """Verify legacy course F-A0010-001 parser extracts 6 course regions, 7-day rows, and identifies source."""
    fixture_path = PROJECT_ROOT / "docs" / "data" / "forecast_fixture.json"
    assert fixture_path.is_file(), "forecast_fixture.json should exist"

    with fixture_path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    normalized = normalize_forecast_dataset(raw_data)

    assert "metadata" in normalized
    assert normalized["metadata"]["source_dataset"] == "F-A0010-001"
    assert normalized["regions"] == EXPECTED_COURSE_REGIONS

    forecasts = normalized["forecasts"]
    assert len(forecasts) == 42, f"Expected 42 rows (6 regions * 7 days), got {len(forecasts)}"

    for row in forecasts:
        assert "regionName" in row
        assert "dataDate" in row
        assert "mint" in row
        assert "maxt" in row
        assert row["regionName"] in EXPECTED_COURSE_REGIONS
        assert isinstance(row["dataDate"], str) and len(row["dataDate"]) == 10  # YYYY-MM-DD
        assert isinstance(row["mint"], (int, float))
        assert isinstance(row["maxt"], (int, float))
        assert row["mint"] <= row["maxt"]


def test_normalize_forecast_dataset_fc0032_003():
    """Verify official F-C0032-003 parser extracts 6 regions, 7-day rows, and MaxT/MinT."""
    sample_fc0032 = {
        "cwaopendata": {
            "Dataid": "C0032-003",
            "Dataset": {
                "Locations": {
                    "Location": [
                        {
                            "LocationName": reg,
                            "WeatherElement": [
                                {
                                    "ElementName": "最高溫度",
                                    "Time": [
                                        {
                                            "StartTime": f"2026-09-{25+i:02d}T00:00:00+0800",
                                            "ElementValue": {"MaxTemperature": str(30 + i)},
                                        }
                                        for i in range(7)
                                    ],
                                },
                                {
                                    "ElementName": "最低溫度",
                                    "Time": [
                                        {
                                            "StartTime": f"2026-09-{25+i:02d}T00:00:00+0800",
                                            "ElementValue": {"MinTemperature": str(20 + i)},
                                        }
                                        for i in range(7)
                                    ],
                                },
                            ],
                        }
                        for reg in EXPECTED_COURSE_REGIONS
                    ]
                }
            }
        }
    }

    normalized = normalize_forecast_dataset(sample_fc0032)

    assert normalized["metadata"]["source_dataset"] == "F-C0032-003"
    assert "F-C0032-003" in normalized["metadata"]["source"]
    assert normalized["regions"] == EXPECTED_COURSE_REGIONS
    assert len(normalized["forecasts"]) == 42

    for row in normalized["forecasts"]:
        assert row["regionName"] in EXPECTED_COURSE_REGIONS
        assert row["mint"] is not None
        assert row["maxt"] is not None
        assert row["mint"] < row["maxt"]


def test_forecast_db_helpers(tmp_path):
    """Verify upsert, list regions, query rows, and payload reconstruction helpers."""
    db_file = tmp_path / "test_helpers.db"
    init_db(db_file)

    sample_rows = [
        {"regionName": "北部地區", "dataDate": "2026-09-25", "mint": 20.0, "maxt": 28.0},
        {"regionName": "北部地區", "dataDate": "2026-09-26", "mint": 21.0, "maxt": 29.0},
        {"regionName": "中部地區", "dataDate": "2026-09-25", "mint": 22.0, "maxt": 31.0},
    ]

    inserted = upsert_forecast_rows(db_file, sample_rows, replace=True)
    assert inserted == 3
    assert forecast_row_count(db_file) == 3

    regions = list_forecast_regions(db_file)
    assert "北部地區" in regions
    assert "中部地區" in regions

    north_rows = query_forecast_rows(db_file, region="北部地區")
    assert len(north_rows) == 2
    assert all(r["regionName"] == "北部地區" for r in north_rows)
    assert north_rows[0]["mint"] == 20.0

    all_rows = query_forecast_rows(db_file, region=None)
    assert len(all_rows) == 3

    payload = forecast_payload_from_db(db_file, region="北部地區")
    assert payload["region"] == "北部地區"
    assert len(payload["forecasts"]) == 2
    assert payload["metadata"]["storage"] == "sqlite"

    # Test UNIQUE(regionName, dataDate) update on conflict
    updated_rows = [
        {"regionName": "北部地區", "dataDate": "2026-09-25", "mint": 18.0, "maxt": 26.0},
    ]
    upsert_forecast_rows(db_file, updated_rows, replace=False)
    assert forecast_row_count(db_file) == 3  # Count unchanged

    refreshed_north = query_forecast_rows(db_file, region="北部地區")
    r0 = [r for r in refreshed_north if r["dataDate"] == "2026-09-25"][0]
    assert r0["mint"] == 18.0
    assert r0["maxt"] == 26.0


def test_forecast_live_integration_and_current_dates():
    """Verify docs/data/forecast.json and data.db both hold live 42-row 6-region F-C0032-003 data."""
    json_path = PROJECT_ROOT / "docs" / "data" / "forecast.json"
    db_path = PROJECT_ROOT / "data.db"

    assert json_path.is_file(), "docs/data/forecast.json must exist"
    assert db_path.is_file(), "data.db must exist"

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Verify source dataset metadata honestly set
    assert data["metadata"]["source_dataset"] == "F-C0032-003"
    assert data["metadata"]["build_mode"] == "live_cwa_api"
    assert data["regions"] == EXPECTED_COURSE_REGIONS
    assert len(data["forecasts"]) == 42
    assert data["metadata"]["total_records"] == 42

    # Verify date span is current/future 7-day data (>= 2026)
    dates = sorted(set(r["dataDate"] for r in data["forecasts"]))
    assert len(dates) == 7
    assert dates[0] >= "2026-09-25"

    db_count = forecast_row_count(db_path)
    assert db_count == 42
    db_regions = list_forecast_regions(db_path)
    assert db_regions == EXPECTED_COURSE_REGIONS

    # Verify database payload reconstruction returns F-C0032-003 metadata
    db_payload = forecast_payload_from_db(db_path)
    assert db_payload["metadata"]["source_dataset"] == "F-C0032-003"
    assert db_payload["metadata"]["build_mode"] == "live_cwa_api"


def test_flask_api_forecast_routes():
    """Verify Flask /api/forecast endpoint returns expected JSON and supports ?region= filter."""
    client = app.test_client()

    # Query all regions
    resp = client.get("/api/forecast")
    assert resp.status_code == 200
    assert resp.is_json
    payload = resp.get_json()
    assert payload["regions"] == EXPECTED_COURSE_REGIONS
    assert len(payload["forecasts"]) == 42
    assert payload["metadata"]["source_dataset"] == "F-C0032-003"

    # Query specific region
    resp_central = client.get("/api/forecast?region=中部地區")
    assert resp_central.status_code == 200
    central_data = resp_central.get_json()
    assert central_data["region"] == "中部地區"
    assert len(central_data["forecasts"]) == 7
    assert all(r["regionName"] == "中部地區" for r in central_data["forecasts"])

    # Query non-existent region returns empty forecasts list gracefully
    resp_empty = client.get("/api/forecast?region=不存在地區")
    assert resp_empty.status_code == 200
    assert len(resp_empty.get_json()["forecasts"]) == 0

    # Static fallback route
    resp_static = client.get("/data/forecast.json")
    assert resp_static.status_code == 200


def test_observation_data_preserved_during_forecast_generation(tmp_path):
    """Verify forecast build does not overwrite or remove weather observations."""
    test_db = tmp_path / "preserve_test.db"
    test_st_json = tmp_path / "stations.json"
    test_fc_json = tmp_path / "forecast.json"
    st_fixture = PROJECT_ROOT / "docs" / "data" / "stations_fixture.json"
    fc_fixture = PROJECT_ROOT / "docs" / "data" / "forecast_fixture.json"

    # Step 1: Build station observation data
    build_dataset(
        output_path=test_st_json,
        fixture_path=st_fixture,
        database_path=test_db,
        fixture_only=True,
    )
    obs_count_before = row_count(test_db)
    assert obs_count_before > 0

    # Step 2: Build forecast data
    build_forecast_dataset(
        output_path=test_fc_json,
        fixture_path=fc_fixture,
        database_path=test_db,
        fixture_only=True,
    )

    # Step 3: Verify observations table remains unchanged
    obs_count_after = row_count(test_db)
    assert obs_count_after == obs_count_before

    # Verify forecast table is populated
    fc_count = forecast_row_count(test_db)
    assert fc_count == 42


def test_honest_fallback_reporting(tmp_path):
    """Verify fixture fallback sets build_mode to fallback_fixture and leaves no fake live marker."""
    test_db = tmp_path / "honest_test.db"
    test_fc_json = tmp_path / "forecast_honest.json"
    fc_fixture = PROJECT_ROOT / "docs" / "data" / "forecast_fixture.json"

    result = build_forecast_dataset(
        output_path=test_fc_json,
        fixture_path=fc_fixture,
        database_path=test_db,
        fixture_only=True,
    )

    assert result["metadata"]["build_mode"] == "fallback_fixture"
    assert result["metadata"]["build_mode"] != "live_cwa_api"
    assert result["metadata"]["source_dataset"] == "F-A0010-001"
