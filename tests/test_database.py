from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from database import (
    init_db,
    latest_observation_time,
    payload_from_db,
    query_sample,
    row_count,
    upsert_payload,
)


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
            "stats": {},
            "counties": ["新竹縣"],
            "color_scale": [],
            "build_mode": "test",
        },
        "stations": [station],
    }


def test_schema_initializes(tmp_path):
    db = tmp_path / "weather.db"
    init_db(db)
    assert db.is_file()
    assert row_count(db) == 0


def test_upsert_and_duplicate_prevention(tmp_path):
    db = tmp_path / "weather.db"
    payload = make_payload("2026-09-24T10:00:00+08:00")
    upsert_payload(db, payload, "test")
    upsert_payload(db, payload, "test")
    assert row_count(db) == 1


def test_multiple_observation_times_are_persisted(tmp_path):
    db = tmp_path / "weather.db"
    upsert_payload(db, make_payload("2026-09-24T10:00:00+08:00", 25.0), "test")
    upsert_payload(db, make_payload("2026-09-24T10:10:00+08:00", 26.0), "test")
    assert row_count(db) == 2
    assert latest_observation_time(db) == "2026-09-24T10:10:00+08:00"


def test_query_by_county(tmp_path):
    db = tmp_path / "weather.db"
    upsert_payload(db, make_payload("2026-09-24T10:00:00+08:00"), "test")
    rows = query_sample(db, county="新竹縣", limit=5)
    assert len(rows) == 1
    assert rows[0]["station_name"] == "測試站"
    assert rows[0]["county"] == "新竹縣"


def test_latest_payload_reconstruction(tmp_path):
    db = tmp_path / "weather.db"
    upsert_payload(db, make_payload("2026-09-24T10:00:00+08:00", 25.0), "test")
    upsert_payload(db, make_payload("2026-09-24T10:10:00+08:00", 26.0), "test")
    payload = payload_from_db(db)
    assert payload["metadata"]["storage"] == "sqlite"
    assert payload["metadata"]["total_stations"] == 1
    assert payload["metadata"]["observation_time"] == "2026-09-24T10:10:00+08:00"
    assert payload["stations"][0]["temperature"] == 26.0
