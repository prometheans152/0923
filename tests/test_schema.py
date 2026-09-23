"""
Tests for generated stations.json schema conformance.
"""

import json
from pathlib import Path


def test_generated_stations_json_schema():
    """Verify generated stations.json has required metadata and station fields."""
    json_path = Path(__file__).resolve().parent.parent / "docs" / "data" / "stations.json"
    assert json_path.is_file(), f"stations.json does not exist at {json_path}"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Metadata check
    assert "metadata" in data
    meta = data["metadata"]
    assert "source" in meta
    assert "generated_at" in meta
    assert "observation_time" in meta
    assert "total_stations" in meta
    assert meta["total_stations"] > 0
    assert "stats" in meta
    assert "max_temperature" in meta["stats"]
    assert "min_temperature" in meta["stats"]
    assert "avg_temperature" in meta["stats"]
    assert "counties" in meta
    assert len(meta["counties"]) >= 10

    # 2. Stations check
    assert "stations" in data
    stations = data["stations"]
    assert len(stations) == meta["total_stations"]

    # Sample station fields
    sample = stations[0]
    required_keys = [
        "station_id",
        "station_name",
        "county",
        "town",
        "lat",
        "lon",
        "obs_time",
        "weather",
        "temperature",
        "humidity",
        "wind_speed",
        "precipitation",
        "color",
        "category",
        "has_temp",
    ]
    for key in required_keys:
        assert key in sample, f"Missing key '{key}' in station schema"

    # Coordinates validity
    for st in stations:
        assert 15.0 <= st["lat"] <= 30.0, f"Lat out of bounds: {st['lat']}"
        assert 115.0 <= st["lon"] <= 125.0, f"Lon out of bounds: {st['lon']}"
        assert st["color"].startswith("#")
