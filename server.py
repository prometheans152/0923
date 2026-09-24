from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

from flask import Flask, abort, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
SEED_JSON = DOCS_DIR / "data" / "stations.json"
SEED_DB = BASE_DIR / "data.db"
SCRIPTS_DIR = BASE_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from database import (
    init_db,
    latest_observation_time,
    payload_from_db,
    query_sample,
    row_count,
    upsert_payload,
)
from fetch_and_build import fetch_from_cwa, get_cwa_api_key
from normalize import normalize_cwa_dataset

app = Flask(__name__, static_folder=None)

REFRESH_SECONDS = 10 * 60
_refresh_lock = threading.Lock()
_last_refresh_monotonic = 0.0


def runtime_db_path() -> Path:
    """Use writable /tmp SQLite on Vercel; use project data.db locally."""
    if os.environ.get("VERCEL"):
        return Path("/tmp/aiot-weather.db")
    return SEED_DB


def _seed_runtime_db(db_path: Path) -> None:
    """Create/seed SQLite without exposing any secret."""
    if db_path.exists():
        init_db(db_path)
        return

    if db_path != SEED_DB and SEED_DB.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SEED_DB, db_path)
        init_db(db_path)
        return

    init_db(db_path)
    if SEED_JSON.exists():
        with SEED_JSON.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        mode = (payload.get("metadata") or {}).get("build_mode") or "seed_json"
        upsert_payload(db_path, payload, source_mode=mode)


def _refresh_live_if_due(db_path: Path, force: bool = False) -> bool:
    """
    Refresh the warm-instance SQLite cache from CWA when a server-side secret exists.

    Vercel /tmp is intentionally treated as ephemeral. A cold instance is reseeded
    and refreshed; durable cloud history would require an external database.
    """
    global _last_refresh_monotonic

    api_key = get_cwa_api_key()
    if not api_key:
        return False

    now = time.monotonic()
    if not force and _last_refresh_monotonic and now - _last_refresh_monotonic < REFRESH_SECONDS:
        return False

    with _refresh_lock:
        now = time.monotonic()
        if not force and _last_refresh_monotonic and now - _last_refresh_monotonic < REFRESH_SECONDS:
            return False

        raw = fetch_from_cwa(api_key)
        if not raw:
            _last_refresh_monotonic = now
            return False

        payload = normalize_cwa_dataset(raw)
        payload["metadata"]["build_mode"] = "live_cwa_api"
        payload["metadata"]["storage"] = "sqlite"
        upsert_payload(db_path, payload, source_mode="live_cwa_api")
        _last_refresh_monotonic = now
        return True


def _prepare_database(refresh: bool = True) -> Path:
    db_path = runtime_db_path()
    _seed_runtime_db(db_path)
    if refresh:
        try:
            _refresh_live_if_due(db_path)
        except Exception as exc:
            # Keep the web app available from already-persisted SQLite data.
            app.logger.warning("CWA refresh failed; serving SQLite cache: %s", type(exc).__name__)
    return db_path


@app.get("/api/weather")
def api_weather():
    """Gate 3 API: GIS data is read from SQLite, optionally refreshed from CWA."""
    db_path = _prepare_database(refresh=True)
    payload = payload_from_db(db_path)
    if not payload.get("stations"):
        return jsonify({"error": "SQLite contains no weather observations"}), 503
    return jsonify(payload)


@app.get("/api/db-check")
def api_db_check():
    """Gate 2 proof: execute a real SQLite query and return a safe sample."""
    db_path = _prepare_database(refresh=True)
    county = (request.args.get("county") or "新竹縣").strip()
    try:
        limit = int(request.args.get("limit") or 5)
    except ValueError:
        limit = 5
    limit = max(1, min(limit, 20))

    return jsonify(
        {
            "database": "sqlite",
            "row_count": row_count(db_path),
            "county": county,
            "latest_observation_time": latest_observation_time(db_path),
            "sample": query_sample(db_path, county=county, limit=limit),
            "persistence_note": (
                "Local data.db persists on disk; Vercel /tmp SQLite is ephemeral per "
                "serverless instance and is reseeded/refreshed when a new instance starts."
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
    _prepare_database(refresh=True)
    app.run(host="127.0.0.1", port=5000, debug=True)
