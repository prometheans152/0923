"""
Fetch and build script for Taiwan CWA Weather Station Dashboard.
Gate 1: fetch/normalize CWA O-A0003-001.
Gate 2: persist the normalized snapshot into SQLite.
NEVER prints, leaks, or logs secret keys.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Optional
import urllib.error
import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from database import (
    latest_observation_time,
    query_sample,
    row_count,
    upsert_forecast_payload,
    upsert_payload,
)
from normalize import normalize_cwa_dataset, normalize_forecast_dataset

CWA_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
CWA_FORECAST_API_URL = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/F-C0032-003"


def get_cwa_api_key() -> Optional[str]:
    """Safely retrieve CWA API key from environment or local .env."""
    for env_name in ["CWA_API_KEY", "CWA_API_TOKEN", "CWA_TOKEN", "CWB_API_KEY"]:
        val = os.environ.get(env_name)
        if val and val.strip() and not val.strip().startswith("YOUR_"):
            return val.strip()

    env_path = PROJECT_ROOT / ".env"
    if env_path.is_file():
        try:
            with env_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if (
                        key in ["CWA_API_KEY", "CWA_API_TOKEN", "CWA_TOKEN"]
                        and value
                        and not value.startswith("YOUR_")
                    ):
                        return value
        except Exception:
            pass

    key_file = PROJECT_ROOT / "api_key.txt"
    if key_file.is_file():
        try:
            with key_file.open("r", encoding="utf-8") as handle:
                val = handle.read().strip()
                if val and not val.startswith("YOUR_"):
                    return val
        except Exception:
            pass

    return None


def fetch_from_cwa(api_key: str) -> Optional[dict]:
    """Fetch raw CWA O-A0003-001 dataset without logging the credential."""
    url = f"{CWA_API_URL}?Authorization={api_key}&format=JSON"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AIoT-WeatherStationDashboard/1.0",
            "Accept": "application/json",
        },
    )
    try:
        print("[INFO] Fetching live data from CWA API (O-A0003-001)...")
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status != 200:
                print(f"[WARN] CWA API responded with HTTP status {resp.status}")
                return None
            payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("success") in [True, "true"]:
                return payload
            print("[WARN] CWA API returned a non-success response.")
    except urllib.error.HTTPError as exc:
        print(f"[WARN] HTTP error fetching CWA data: HTTP {exc.code}")
    except urllib.error.URLError as exc:
        print(f"[WARN] Network error connecting to CWA API: {exc.reason}")
    except Exception as exc:
        print(f"[WARN] Unexpected error fetching CWA data: {type(exc).__name__}")
    return None


def fetch_forecast_from_cwa(api_key: str) -> Optional[dict]:
    """Fetch raw CWA F-C0032-003 dataset without logging the credential."""
    url = f"{CWA_FORECAST_API_URL}?Authorization={api_key}&downloadType=WEB&format=JSON"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AIoT-WeatherStationDashboard/1.0",
            "Accept": "application/json",
        },
    )
    try:
        print("[INFO] Fetching live forecast data from CWA API (F-C0032-003)...")
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                if (
                    payload.get("cwaopendata")
                    or payload.get("records")
                    or payload.get("success") in [True, "true"]
                ):
                    return payload
            print(f"[WARN] CWA forecast API responded with HTTP status {resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"[WARN] HTTP error fetching CWA forecast: HTTP {exc.code}")
    except urllib.error.URLError as exc:
        print(f"[WARN] Network error connecting to CWA forecast API: {exc.reason}")
    except Exception as exc:
        print(f"[WARN] Unexpected error fetching CWA forecast: {type(exc).__name__}")
    return None


def load_fixture(fixture_path: Path) -> dict:
    if not fixture_path.is_file():
        raise FileNotFoundError(f"Fixture file not found at: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_dataset(
    output_path: Path,
    fixture_path: Path,
    database_path: Path,
    fixture_only: bool = False,
) -> dict:
    raw_data = None
    data_source_mode = "fixture"

    if not fixture_only:
        api_key = get_cwa_api_key()
        if api_key:
            print("[INFO] CWA API key detected in the secure environment.")
            raw_data = fetch_from_cwa(api_key)
            if raw_data:
                data_source_mode = "live_cwa_api"
        else:
            print("[INFO] No CWA API key found; using bundled fallback fixture.")
    else:
        print("[INFO] --fixture-only specified; skipping network fetch.")

    if raw_data is None:
        print(f"[INFO] Loading fallback fixture from {fixture_path}...")
        raw_data = load_fixture(fixture_path)
        data_source_mode = "fallback_fixture"

    normalized = normalize_cwa_dataset(raw_data)
    normalized["metadata"]["build_mode"] = data_source_mode
    normalized["metadata"]["storage"] = "sqlite"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)

    inserted = upsert_payload(database_path, normalized, data_source_mode)

    total_st = normalized["metadata"]["total_stations"]
    valid_st = normalized["metadata"]["valid_temp_stations"]
    max_t = normalized["metadata"]["stats"]["max_temperature"]
    min_t = normalized["metadata"]["stats"]["min_temperature"]
    avg_t = normalized["metadata"]["stats"]["avg_temperature"]
    obs_time = normalized["metadata"].get("observation_time")

    print(f"[SUCCESS] Built station JSON -> {output_path}")
    print(f"[SUCCESS] Persisted snapshot to SQLite -> {database_path}")
    print(f"          - Mode: {data_source_mode}")
    print(f"          - Observation time: {obs_time}")
    print(f"          - Snapshot stations: {total_st} (Valid temp: {valid_st})")
    print(
        f"          - Temp range: {min_t.get('value')}°C ({min_t.get('station_name')}) "
        f"~ {max_t.get('value')}°C ({max_t.get('station_name')})"
    )
    print(f"          - Avg temp: {avg_t}°C")
    print(f"          - SQLite upserted rows: {inserted}")
    print(f"          - SQLite total observation rows: {row_count(database_path)}")
    print(f"          - SQLite latest observation: {latest_observation_time(database_path)}")
    sample = query_sample(database_path, county="新竹縣", limit=3)
    if sample:
        print("[VERIFY] SQLite query sample (新竹縣):")
        for row in sample:
            print(
                f"          {row['station_name']} | {row['obs_time']} | "
                f"{row['temperature']}°C | RH {row['humidity']}"
            )
    return normalized


def build_forecast_dataset(
    output_path: Path,
    fixture_path: Path,
    database_path: Path,
    fixture_only: bool = False,
) -> dict:
    raw_data = None
    data_source_mode = "fixture"

    if not fixture_only:
        api_key = get_cwa_api_key()
        if api_key:
            print("[INFO] CWA API key detected in the secure environment for forecast.")
            raw_data = fetch_forecast_from_cwa(api_key)
            if raw_data:
                data_source_mode = "live_cwa_api"
            else:
                print(
                    "[WARN] Live CWA forecast API fetch failed or returned no data; "
                    "falling back to bundled forecast fixture."
                )
        else:
            print("[INFO] No CWA API key found; using bundled fallback forecast fixture.")
    else:
        print("[INFO] --fixture-only specified; skipping forecast network fetch.")

    if raw_data is None:
        print(f"[INFO] Loading fallback forecast fixture from {fixture_path}...")
        raw_data = load_fixture(fixture_path)
        data_source_mode = "fallback_fixture"

    normalized = normalize_forecast_dataset(raw_data)
    normalized["metadata"]["build_mode"] = data_source_mode
    normalized["metadata"]["storage"] = "sqlite"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)

    inserted = upsert_forecast_payload(database_path, normalized, replace=True)

    total_regions = len(normalized.get("regions", []))
    total_rows = len(normalized.get("forecasts", []))

    print(f"[SUCCESS] Built forecast JSON -> {output_path}")
    print(f"[SUCCESS] Persisted forecast to SQLite -> {database_path}")
    print(f"          - Mode: {data_source_mode}")
    print(f"          - Regions: {total_regions}")
    print(f"          - Total forecast rows: {total_rows}")
    print(f"          - SQLite upserted rows: {inserted}")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch CWA O-A0003-001 and F-A0010-001, normalize them, and persist them in SQLite"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=PROJECT_ROOT / "docs" / "data" / "stations.json",
    )
    parser.add_argument(
        "--fixture",
        "-f",
        type=Path,
        default=PROJECT_ROOT / "docs" / "data" / "stations_fixture.json",
    )
    parser.add_argument(
        "--database",
        "-d",
        type=Path,
        default=PROJECT_ROOT / "data.db",
    )
    parser.add_argument("--fixture-only", action="store_true")
    parser.add_argument(
        "--forecast-output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "data" / "forecast.json",
    )
    parser.add_argument(
        "--forecast-fixture",
        type=Path,
        default=PROJECT_ROOT / "docs" / "data" / "forecast_fixture.json",
    )
    args = parser.parse_args()

    build_dataset(
        output_path=args.output,
        fixture_path=args.fixture,
        database_path=args.database,
        fixture_only=args.fixture_only,
    )
    build_forecast_dataset(
        output_path=args.forecast_output,
        fixture_path=args.forecast_fixture,
        database_path=args.database,
        fixture_only=args.fixture_only,
    )


if __name__ == "__main__":
    main()
