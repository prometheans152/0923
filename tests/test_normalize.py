"""
Unit tests for data normalization and missing/invalid value handling.
"""

import sys
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from normalize import (
    clean_number,
    extract_coordinates,
    normalize_station,
    normalize_cwa_dataset,
)


def test_clean_number_sentinels():
    """Verify CWA sentinel values (-99, -999, etc.) are converted to None."""
    assert clean_number(-99) is None
    assert clean_number(-99.0) is None
    assert clean_number("-99") is None
    assert clean_number(-999) is None
    assert clean_number(None) is None
    assert clean_number("") is None
    assert clean_number("invalid") is None


def test_clean_number_valid():
    """Verify normal numbers are properly parsed and rounded."""
    assert clean_number(28.456) == 28.46
    assert clean_number("27.3") == 27.3
    assert clean_number(0) == 0.0
    assert clean_number("0.0") == 0.0


def test_clean_number_bounds():
    """Verify bounds filtering for impossible weather measurements."""
    assert clean_number(120.0, min_val=-40.0, max_val=60.0) is None  # 120°C impossible
    assert clean_number(-50.0, min_val=-40.0, max_val=60.0) is None


def test_extract_coordinates():
    """Verify extraction of lat/lon from direct fields and Coordinates list."""
    # Direct fields
    lat, lon = extract_coordinates({"StationLatitude": 25.03, "StationLongitude": 121.56})
    assert lat == 25.03
    assert lon == 121.56

    # Coordinates list
    lat2, lon2 = extract_coordinates({
        "Coordinates": [
            {"StationLatitude": 24.15, "StationLongitude": 120.68}
        ]
    })
    assert lat2 == 24.15
    assert lon2 == 120.68

    # Missing / Invalid
    lat3, lon3 = extract_coordinates({"StationLatitude": -99, "StationLongitude": 121.5})
    assert lat3 is None
    assert lon3 is None


def test_normalize_station_valid():
    """Verify full station normalization with valid fields."""
    raw = {
        "StationId": "466920",
        "StationName": "臺北",
        "GeoInfo": {
            "CountyName": "臺北市",
            "TownName": "中正區",
            "StationAltitude": "5.3",
            "Coordinates": [{"StationLatitude": 25.0376, "StationLongitude": 121.5148}],
        },
        "ObsTime": {"DateTime": "2026-09-23T17:00:00+08:00"},
        "WeatherElement": {
            "Weather": "晴",
            "AirTemperature": "28.5",
            "RelativeHumidity": "65",
            "AirPressure": "1010.5",
            "WindSpeed": "3.5",
            "PeakGustSpeed": "7.8",
            "Precipitation": "0.0",
        },
    }
    st = normalize_station(raw)
    assert st is not None
    assert st["station_id"] == "466920"
    assert st["station_name"] == "臺北"
    assert st["county"] == "臺北市"
    assert st["temperature"] == 28.5
    assert st["humidity"] == 65.0
    assert st["has_temp"] is True
    assert st["color"].startswith("#")


def test_normalize_station_missing_coords_dropped():
    """Verify stations without valid coordinates are dropped to avoid bad map points."""
    raw = {
        "StationId": "UNKNOWN",
        "StationName": "測試站",
        "GeoInfo": {"StationLatitude": -99, "StationLongitude": -99},
        "WeatherElement": {"AirTemperature": 25.0},
    }
    assert normalize_station(raw) is None


def test_normalize_dataset_summary_stats():
    """Verify dataset summary statistics (max, min, avg, count) calculation."""
    sample = {
        "records": {
            "Station": [
                {
                    "StationId": "S1",
                    "StationName": "高溫站",
                    "GeoInfo": {"CountyName": "高雄市", "Coordinates": [{"StationLatitude": 22.5, "StationLongitude": 120.3}]},
                    "WeatherElement": {"AirTemperature": 32.0, "WindSpeed": 5.0, "Precipitation": 0},
                },
                {
                    "StationId": "S2",
                    "StationName": "低溫站",
                    "GeoInfo": {"CountyName": "南投縣", "Coordinates": [{"StationLatitude": 23.5, "StationLongitude": 120.9}]},
                    "WeatherElement": {"AirTemperature": 8.0, "WindSpeed": 2.0, "Precipitation": 10.0},
                },
                {
                    "StationId": "S3",
                    "StationName": "缺溫站",
                    "GeoInfo": {"CountyName": "臺中市", "Coordinates": [{"StationLatitude": 24.1, "StationLongitude": 120.6}]},
                    "WeatherElement": {"AirTemperature": -99, "WindSpeed": 1.0, "Precipitation": 0},
                },
            ]
        }
    }
    norm = normalize_cwa_dataset(sample)
    meta = norm["metadata"]
    assert meta["total_stations"] == 3
    assert meta["valid_temp_stations"] == 2
    assert meta["stats"]["max_temperature"]["value"] == 32.0
    assert meta["stats"]["max_temperature"]["station_name"] == "高溫站"
    assert meta["stats"]["min_temperature"]["value"] == 8.0
    assert meta["stats"]["min_temperature"]["station_name"] == "低溫站"
    assert meta["stats"]["avg_temperature"] == 20.0
    assert meta["stats"]["max_precipitation"]["value"] == 10.0
