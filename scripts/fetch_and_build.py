"""
Fetch and build script for Taiwan CWA Weather Station Dashboard.
Safely queries CWA API dataset O-A0003-001 or falls back to bundled fixture.
NEVER prints, leaks, or logs secret keys.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Optional
import urllib.request
import urllib.error

# Ensure scripts directory is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from normalize import normalize_cwa_dataset

CWA_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"


def get_cwa_api_key() -> Optional[str]:
    """
    Safely retrieves CWA API key from environment or local .env file.
    Does NOT print or log the key.
    """
    # 1. Environment variable (e.g. GitHub Actions secret, user terminal export)
    for env_name in ["CWA_API_KEY", "CWA_API_TOKEN", "CWA_TOKEN", "CWB_API_KEY"]:
        val = os.environ.get(env_name)
        if val and val.strip() and not val.strip().startswith("YOUR_"):
            return val.strip()

    # 2. Local .env file in project root
    env_paths = [
        PROJECT_ROOT / ".env",
    ]
    for p in env_paths:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("\"'")
                            if k in ["CWA_API_KEY", "CWA_API_TOKEN", "CWA_TOKEN"] and v and not v.startswith("YOUR_"):
                                return v
            except Exception:
                pass

    return None


def fetch_from_cwa(api_key: str) -> Optional[dict]:
    """
    Fetches raw CWA O-A0003-001 dataset using urllib (no external deps required).
    """
    url = f"{CWA_API_URL}?Authorization={api_key}&format=JSON"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AIoT-WeatherStationDashboard/1.0", "Accept": "application/json"}
    )
    try:
        print("[INFO] Fetching live data from CWA API (O-A0003-001)...")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                if payload.get("success") in [True, "true"]:
                    return payload
                else:
                    print(f"[WARN] CWA API returned non-success response: {payload.get('message', 'unknown')}")
            else:
                print(f"[WARN] CWA API responded with HTTP status {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"[WARN] HTTP error fetching CWA data: HTTP {e.code}")
    except urllib.error.URLError as e:
        print(f"[WARN] Network error connecting to CWA API: {e.reason}")
    except Exception as e:
        print(f"[WARN] Unexpected error fetching CWA data: {type(e).__name__}")

    return None


def load_fixture(fixture_path: Path) -> dict:
    """Loads bundled fallback fixture."""
    if not fixture_path.is_file():
        raise FileNotFoundError(f"Fixture file not found at: {fixture_path}")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dataset(
    output_path: Path,
    fixture_path: Path,
    fixture_only: bool = False,
) -> dict:
    """
    Orchestrates fetching (or fixture loading), normalizing, and saving dataset.
    """
    raw_data = None
    data_source_mode = "fixture"

    if not fixture_only:
        api_key = get_cwa_api_key()
        if api_key:
            print("[INFO] Local CWA API key detected in safe environment.")
            raw_data = fetch_from_cwa(api_key)
            if raw_data:
                data_source_mode = "live_cwa_api"
        else:
            print("[INFO] No CWA API key found in environment or local .env.")
            print("[INFO] Using bundled high-fidelity fallback fixture.")
    else:
        print("[INFO] --fixture-only specified; skipping network fetch.")

    if raw_data is None:
        print(f"[INFO] Loading fallback fixture from {fixture_path}...")
        raw_data = load_fixture(fixture_path)
        data_source_mode = "fallback_fixture"

    normalized = normalize_cwa_dataset(raw_data)
    normalized["metadata"]["build_mode"] = data_source_mode

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    total_st = normalized["metadata"]["total_stations"]
    valid_st = normalized["metadata"]["valid_temp_stations"]
    max_t = normalized["metadata"]["stats"]["max_temperature"]
    min_t = normalized["metadata"]["stats"]["min_temperature"]
    avg_t = normalized["metadata"]["stats"]["avg_temperature"]

    print(f"[SUCCESS] Built station dataset -> {output_path}")
    print(f"          - Mode: {data_source_mode}")
    print(f"          - Total stations: {total_st} (Valid temp: {valid_st})")
    print(f"          - Temp range: {min_t.get('value')}°C ({min_t.get('station_name')}) ~ {max_t.get('value')}°C ({max_t.get('station_name')})")
    print(f"          - Avg temp: {avg_t}°C")

    return normalized


def main():
    parser = argparse.ArgumentParser(description="Fetch and normalize CWA O-A0003-001 weather stations")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=PROJECT_ROOT / "docs" / "data" / "stations.json",
        help="Target output JSON path (default: docs/data/stations.json)",
    )
    parser.add_argument(
        "--fixture",
        "-f",
        type=Path,
        default=PROJECT_ROOT / "docs" / "data" / "stations_fixture.json",
        help="Fallback fixture path (default: docs/data/stations_fixture.json)",
    )
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help="Force using fixture without querying CWA API",
    )
    args = parser.parse_args()

    build_dataset(
        output_path=args.output,
        fixture_path=args.fixture,
        fixture_only=args.fixture_only,
    )


if __name__ == "__main__":
    main()
