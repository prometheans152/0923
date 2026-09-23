from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
DATA_FILE = DOCS_DIR / "data" / "stations.json"

app = Flask(__name__, static_folder=None)


@app.get("/api/weather")
def api_weather():
    """Expose the same sanitized station payload used by the frontend."""
    if not DATA_FILE.exists():
        return jsonify({"error": "stations.json not found"}), 404

    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return jsonify(json.load(handle))


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
    app.run(host="127.0.0.1", port=5000, debug=True)
