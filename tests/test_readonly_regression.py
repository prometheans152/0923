"""Regression tests for strict read-only database connections and serverless safety.

Verifies:
1. connect_readonly on non-existent paths raises error and creates no file/dir.
2. connect_readonly properly URI-encodes paths containing spaces and '#' (Path.resolve().as_uri()).
3. connect_readonly never falls back to a read-write connection.
4. Read/query helpers in database.py never call init_db or mkdir.
5. All three API endpoints and forecast region query succeed on bundled DB without RW / init_db.
6. Missing or corrupt DB returns safe JSON 503 without leaking host paths and without auto-creating DB.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import database
from database import (
    connect_readonly,
    forecast_payload_from_db,
    forecast_row_count,
    init_db,
    latest_observation_time,
    list_forecast_regions,
    payload_from_db,
    query_forecast_rows,
    query_sample,
    row_count,
    upsert_forecast_payload,
    upsert_payload,
)
import server


def test_connect_readonly_nonexistent_file_raises_and_creates_nothing(tmp_path):
    """connect_readonly on a non-existent file must raise FileNotFoundError and not create file or dir."""
    missing_dir = tmp_path / "does_not_exist"
    missing_file = missing_dir / "missing.db"

    with pytest.raises(FileNotFoundError):
        connect_readonly(missing_file)

    assert not missing_file.exists(), "connect_readonly must not create the missing db file"
    assert not missing_dir.exists(), "connect_readonly must not create parent directories"


def test_connect_readonly_path_with_special_characters(tmp_path):
    """connect_readonly must properly encode paths with spaces and '#' using as_uri(), strictly read-only."""
    special_dir = tmp_path / "space dir#special"
    special_dir.mkdir(parents=True, exist_ok=True)
    db_file = special_dir / "weather#2026.db"

    # Initialize a valid database
    init_db(db_file)
    with database.connect(db_file) as conn:
        conn.execute("CREATE TABLE sample_data (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO sample_data (val) VALUES ('test_val')")

    # Connect read-only
    ro_conn = connect_readonly(db_file)
    try:
        cur = ro_conn.cursor()
        cur.execute("SELECT val FROM sample_data")
        row = cur.fetchone()
        assert row is not None
        assert row["val"] == "test_val"

        # Strictly read-only: any write must raise sqlite3.OperationalError
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("INSERT INTO sample_data (val) VALUES ('illegal_write')")
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("CREATE TABLE ro_violation (id INT)")
    finally:
        ro_conn.close()


def test_connect_readonly_never_falls_back_to_readwrite(tmp_path):
    """A failed read-only connection must never trigger a second, writable connection."""
    db_file = tmp_path / "strict_ro.db"
    init_db(db_file)

    with patch.object(
        database.sqlite3, "connect",
        side_effect=sqlite3.OperationalError("simulated read-only connection failure"),
    ) as connect_spy:
        with pytest.raises(sqlite3.OperationalError):
            connect_readonly(db_file)

    connect_spy.assert_called_once()
    assert connect_spy.call_args.kwargs.get("uri") is True
    assert connect_spy.call_args.args[0] == db_file.resolve().as_uri() + "?mode=ro"


def test_query_helpers_do_not_call_init_db(tmp_path):
    """Query/read helpers must not call init_db or attempt writes."""
    db_file = tmp_path / "helpers_test.db"
    init_db(db_file)

    # Seed minimal data
    station_payload = {
        "metadata": {
            "source": "test",
            "observation_time": "2026-09-25T12:00:00+08:00",
            "build_mode": "test",
        },
        "stations": [
            {
                "station_id": "TEST01",
                "station_name": "測試",
                "county": "新竹縣",
                "town": "竹北",
                "lat": 24.8,
                "lon": 121.0,
                "obs_time": "2026-09-25T12:00:00+08:00",
                "weather": "晴",
                "temperature": 25.0,
                "humidity": 60.0,
                "has_temp": True,
            }
        ],
    }
    upsert_payload(db_file, station_payload, source_mode="test")

    fc_payload = {
        "metadata": {
            "source": "test",
            "source_dataset": "F-C0032-003",
            "build_mode": "test",
        },
        "regions": ["北部地區"],
        "forecasts": [
            {"regionName": "北部地區", "dataDate": "2026-09-25", "mint": 22.0, "maxt": 30.0}
        ],
    }
    upsert_forecast_payload(db_file, fc_payload)

    def forbidden_init_db(*args, **kwargs):
        raise AssertionError("init_db must not be called during read/query operations!")

    with patch.object(database, "init_db", side_effect=forbidden_init_db):
        assert row_count(db_file) == 1
        assert latest_observation_time(db_file) == "2026-09-25T12:00:00+08:00"
        assert len(query_sample(db_file, county="新竹縣")) == 1

        p_obs = payload_from_db(db_file)
        assert len(p_obs["stations"]) == 1
        assert p_obs["metadata"]["storage"] == "sqlite"

        assert forecast_row_count(db_file) == 1
        assert list_forecast_regions(db_file) == ["北部地區"]
        assert len(query_forecast_rows(db_file, region="北部地區")) == 1

        p_fc = forecast_payload_from_db(db_file, region="北部地區")
        assert len(p_fc["forecasts"]) == 1
        assert p_fc["metadata"]["storage"] == "sqlite"


def test_apis_succeed_with_existing_bundled_db_in_readonly_mode(tmp_path):
    """API reads preserve an isolated bundled snapshot without initialization or writable connections."""
    db_file = tmp_path / "bundled.db"
    original_bytes = (PROJECT_ROOT / "data.db").read_bytes()
    db_file.write_bytes(original_bytes)
    expected_stations = row_count(db_file)
    expected_forecasts = forecast_row_count(db_file)
    expected_north = len(query_forecast_rows(db_file, region="北部地區"))
    assert expected_stations > 0 and expected_forecasts > 0 and expected_north > 0

    def forbidden_init_db(*args, **kwargs):
        raise AssertionError("Server GET endpoint must not call init_db!")

    def forbidden_connect(*args, **kwargs):
        raise AssertionError("Server GET endpoint must not call read-write connect()!")

    with patch.object(server, "DATA_DB", db_file), \
         patch.object(database, "init_db", side_effect=forbidden_init_db), \
         patch.object(database, "connect", side_effect=forbidden_connect):
        client = server.app.test_client()

        res_w = client.get("/api/weather")
        assert res_w.status_code == 200
        w_data = res_w.get_json()
        assert w_data["metadata"]["storage"] == "sqlite"
        assert len(w_data["stations"]) == expected_stations

        res_f = client.get("/api/forecast")
        assert res_f.status_code == 200
        f_data = res_f.get_json()
        assert f_data["metadata"]["storage"] == "sqlite"
        assert len(f_data["forecasts"]) == expected_forecasts

        res_fr = client.get("/api/forecast?region=北部地區")
        assert res_fr.status_code == 200
        fr_data = res_fr.get_json()
        assert len(fr_data["forecasts"]) == expected_north
        assert all(row["regionName"] == "北部地區" for row in fr_data["forecasts"])

        res_db = client.get("/api/db-check?county=新竹縣&limit=3")
        assert res_db.status_code == 200
        db_data = res_db.get_json()
        assert db_data["database"] == "sqlite"
        assert db_data["row_count"] == expected_stations

    assert db_file.read_bytes() == original_bytes


def test_server_missing_or_corrupt_db_returns_safe_503_and_no_leak(tmp_path):
    """Missing or corrupt DB must return 503 JSON without auto-creating DB or leaking paths."""
    missing_db = tmp_path / "no_such_database.db"

    client = server.app.test_client()

    with patch.object(server, "DATA_DB", missing_db):
        for route in ["/api/weather", "/api/forecast", "/api/db-check"]:
            res = client.get(route)
            assert res.status_code == 503, f"Expected 503 on missing DB for {route}, got {res.status_code}"
            assert res.is_json
            data = res.get_json()
            assert "error" in data
            # Check host paths are not leaked in error response
            err_msg = str(data["error"])
            assert str(missing_db) not in err_msg
            assert str(tmp_path) not in err_msg
            assert not missing_db.exists(), f"Endpoint {route} must not auto-create database"

    corrupt_db = tmp_path / "corrupt.db"
    corrupt_db.write_text("NOT A VALID SQLITE DATABASE FILE", encoding="utf-8")

    with patch.object(server, "DATA_DB", corrupt_db):
        for route in ["/api/weather", "/api/forecast", "/api/db-check"]:
            res = client.get(route)
            assert res.status_code == 503, f"Expected 503 on corrupt DB for {route}, got {res.status_code}"
            assert res.is_json
            data = res.get_json()
            assert "error" in data
            err_msg = str(data["error"])
            assert str(corrupt_db) not in err_msg
            assert str(tmp_path) not in err_msg
