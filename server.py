from __future__ import annotations

import sqlite3
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
    latest_observation_time,
    payload_from_db,
    query_sample,
    row_count,
)

app = Flask(__name__, static_folder=None)


def get_db_path() -> Path:
    """Return path to bundled data.db snapshot; strictly validates existence without writing."""
    if not DATA_DB.is_file():
        raise FileNotFoundError("Weather database snapshot not found")
    return DATA_DB


@app.get("/api/weather")
def api_weather():
    """Gate 3 API: GIS data is read directly from SQLite (data.db)."""
    try:
        db_path = get_db_path()
        payload = payload_from_db(db_path)
        if not payload.get("stations"):
            return jsonify({"error": "SQLite contains no weather observations"}), 503
        return jsonify(payload)
    except (OSError, sqlite3.Error):
        return jsonify({"error": "Weather database snapshot unavailable"}), 503


@app.get("/api/forecast")
def api_forecast():
    """Return 7-day regional temperature forecasts from SQLite (data.db), optionally filtered by region."""
    try:
        db_path = get_db_path()
        region = request.args.get("region")
        if region:
            region = region.strip()
        payload = forecast_payload_from_db(db_path, region=region)
        return jsonify(payload)
    except (OSError, sqlite3.Error):
        return jsonify({"error": "Forecast database snapshot unavailable"}), 503


@app.get("/api/db-check")
def api_db_check():
    """Gate 2 proof: execute a real SQLite query and return a safe sample."""
    try:
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
    except (OSError, sqlite3.Error):
        return jsonify({"error": "Database check snapshot unavailable"}), 503


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
    if not DATA_DB.is_file():
        print("[WARN] data.db not found. Please run 'python scripts/fetch_and_build.py' first.")
    app.run(host="127.0.0.1", port=5000, debug=True)
