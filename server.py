from __future__ import annotations

import json
from pathlib import Path
import sys

from flask import Flask, abort, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
SEED_JSON = DOCS_DIR / "data" / "stations.json"
FORECAST_JSON = DOCS_DIR / "data" / "forecast.json"
DATA_DB = BASE_DIR / "data.db"
SCRIPTS_DIR = BASE_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from database import (
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

app = Flask(__name__, static_folder=None)


def get_db_path() -> Path:
    """Return path to data.db; seed if missing."""
    if not DATA_DB.exists():
        if SEED_JSON.exists():
            with SEED_JSON.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            mode = (payload.get("metadata") or {}).get("build_mode") or "seed_json"
            upsert_payload(DATA_DB, payload, source_mode=mode, replace=True)
        else:
            init_db(DATA_DB)

    init_db(DATA_DB)
    if forecast_row_count(DATA_DB) == 0 and FORECAST_JSON.exists():
        try:
            with FORECAST_JSON.open("r", encoding="utf-8") as handle:
                f_payload = json.load(handle)
            upsert_forecast_payload(DATA_DB, f_payload, replace=False)
        except Exception:
            pass

    return DATA_DB


@app.get("/api/weather")
def api_weather():
    """Gate 3 API: GIS data is read directly from SQLite (data.db)."""
    db_path = get_db_path()
    payload = payload_from_db(db_path)
    if not payload.get("stations"):
        return jsonify({"error": "SQLite contains no weather observations"}), 503
    return jsonify(payload)


@app.get("/api/forecast")
def api_forecast():
    """Return 7-day regional temperature forecasts from SQLite (data.db), optionally filtered by region."""
    db_path = get_db_path()
    region = request.args.get("region")
    if region:
        region = region.strip()
    payload = forecast_payload_from_db(db_path, region=region)
    return jsonify(payload)


@app.get("/api/db-check")
def api_db_check():
    """Gate 2 proof: execute a real SQLite query and return a safe sample."""
    db_path = get_db_path()
    county = (request.args.get("county") or "新竹縣").strip()
    try:
        limit = int(request.args.get("limit") or 5)
    except ValueError:
        limit = 5
    limit = max(1, min(limit, 20))

    return jsonify(
        {
            "database": "sqlite",
            "db_path": str(db_path.name),
            "row_count": row_count(db_path),
            "county": county,
            "latest_observation_time": latest_observation_time(db_path),
            "sample": query_sample(db_path, county=county, limit=limit),
            "persistence_note": (
                "Vercel bundles data.db as a read-only SQLite snapshot. "
                "Runtime history writes are not durable in serverless; for historical persistence, use an external database."
            ),
        }
    )


@app.get("/")
def index():
    return send_from_directory(DOCS_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    target = DOCS_DIR / path
    if target.is_file():
        return send_from_directory(DOCS_DIR, path)
    abort(404)


if __name__ == "__main__":
    get_db_path()
    app.run(host="127.0.0.1", port=5000, debug=True)
