"""SQLite persistence for AIoT Week 3 weather observations.

Gate 2 requires fetched CWA observations to be persisted in SQLite and queryable.
No secrets are stored in this database.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

COLOR_SCALE = [
    {"min": None, "max": 10.0, "color": "#2563EB", "label": "嚴寒 (<10°C)"},
    {"min": 10.0, "max": 15.0, "color": "#06B6D4", "label": "寒冷 (10-15°C)"},
    {"min": 15.0, "max": 20.0, "color": "#10B981", "label": "涼爽 (15-20°C)"},
    {"min": 20.0, "max": 25.0, "color": "#EAB308", "label": "舒適 (20-25°C)"},
    {"min": 25.0, "max": 30.0, "color": "#F97316", "label": "溫暖 (25-30°C)"},
    {"min": 30.0, "max": 35.0, "color": "#EF4444", "label": "炎熱 (30-35°C)"},
    {"min": 35.0, "max": None, "color": "#991B1B", "label": "酷熱 (>35°C)"},
]


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                station_id TEXT NOT NULL,
                station_name TEXT NOT NULL,
                county TEXT,
                town TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                altitude REAL,
                obs_time TEXT NOT NULL,
                weather TEXT,
                temperature REAL,
                humidity REAL,
                pressure REAL,
                wind_speed REAL,
                wind_direction REAL,
                gust_speed REAL,
                precipitation REAL,
                uv_index REAL,
                color TEXT,
                category TEXT,
                has_temp INTEGER NOT NULL DEFAULT 0,
                source_mode TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (station_id, obs_time)
            );

            CREATE INDEX IF NOT EXISTS idx_observations_obs_time
                ON observations(obs_time);
            CREATE INDEX IF NOT EXISTS idx_observations_county
                ON observations(county);
            CREATE INDEX IF NOT EXISTS idx_observations_station
                ON observations(station_id);

            CREATE TABLE IF NOT EXISTS snapshots (
                obs_time TEXT NOT NULL,
                source_mode TEXT NOT NULL,
                generated_at TEXT,
                station_count INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (obs_time, source_mode)
            );
            """
        )


def upsert_payload(
    db_path: Path | str,
    payload: Dict[str, Any],
    source_mode: Optional[str] = None,
) -> int:
    init_db(db_path)
    metadata = payload.get("metadata") or {}
    mode = source_mode or metadata.get("build_mode") or "unknown"
    now = datetime.now(timezone.utc).isoformat()
    stations = payload.get("stations") or []

    rows = []
    for st in stations:
        station_id = str(st.get("station_id") or "").strip()
        obs_time = str(st.get("obs_time") or metadata.get("observation_time") or "").strip()
        if not station_id or not obs_time:
            continue
        rows.append(
            (
                station_id,
                str(st.get("station_name") or ""),
                st.get("county"),
                st.get("town"),
                st.get("lat"),
                st.get("lon"),
                st.get("altitude"),
                obs_time,
                st.get("weather"),
                st.get("temperature"),
                st.get("humidity"),
                st.get("pressure"),
                st.get("wind_speed"),
                st.get("wind_direction"),
                st.get("gust_speed"),
                st.get("precipitation"),
                st.get("uv_index"),
                st.get("color"),
                st.get("category"),
                1 if st.get("has_temp") else 0,
                mode,
                now,
            )
        )

    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO observations (
                station_id, station_name, county, town, lat, lon, altitude,
                obs_time, weather, temperature, humidity, pressure, wind_speed,
                wind_direction, gust_speed, precipitation, uv_index, color,
                category, has_temp, source_mode, ingested_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(station_id, obs_time) DO UPDATE SET
                station_name=excluded.station_name,
                county=excluded.county,
                town=excluded.town,
                lat=excluded.lat,
                lon=excluded.lon,
                altitude=excluded.altitude,
                weather=excluded.weather,
                temperature=excluded.temperature,
                humidity=excluded.humidity,
                pressure=excluded.pressure,
                wind_speed=excluded.wind_speed,
                wind_direction=excluded.wind_direction,
                gust_speed=excluded.gust_speed,
                precipitation=excluded.precipitation,
                uv_index=excluded.uv_index,
                color=excluded.color,
                category=excluded.category,
                has_temp=excluded.has_temp,
                source_mode=excluded.source_mode,
                ingested_at=excluded.ingested_at
            """,
            rows,
        )

        obs_time = str(metadata.get("observation_time") or "")
        if obs_time:
            conn.execute(
                """
                INSERT INTO snapshots (
                    obs_time, source_mode, generated_at, station_count,
                    metadata_json, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(obs_time, source_mode) DO UPDATE SET
                    generated_at=excluded.generated_at,
                    station_count=excluded.station_count,
                    metadata_json=excluded.metadata_json,
                    ingested_at=excluded.ingested_at
                """,
                (
                    obs_time,
                    mode,
                    metadata.get("generated_at"),
                    len(rows),
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                ),
            )
    return len(rows)


def row_count(db_path: Path | str) -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0])


def latest_observation_time(db_path: Path | str) -> Optional[str]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT MAX(obs_time) AS obs_time FROM observations").fetchone()
        return row["obs_time"] if row and row["obs_time"] else None


def query_sample(
    db_path: Path | str,
    county: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    init_db(db_path)
    limit = max(1, min(int(limit), 50))
    with connect(db_path) as conn:
        if county:
            rows = conn.execute(
                """
                SELECT station_id, station_name, county, town, obs_time,
                       temperature, humidity, wind_speed
                FROM observations
                WHERE county = ?
                ORDER BY obs_time DESC, station_name
                LIMIT ?
                """,
                (county, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT station_id, station_name, county, town, obs_time,
                       temperature, humidity, wind_speed
                FROM observations
                ORDER BY obs_time DESC, station_name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def _latest_rows(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT o.*
        FROM observations o
        JOIN (
            SELECT station_id, MAX(obs_time) AS max_obs_time
            FROM observations
            GROUP BY station_id
        ) latest
          ON latest.station_id = o.station_id
         AND latest.max_obs_time = o.obs_time
        ORDER BY
            CASE WHEN o.temperature IS NULL THEN 1 ELSE 0 END,
            o.temperature DESC,
            o.county,
            o.station_name
        """
    ).fetchall()


def payload_from_db(db_path: Path | str) -> Dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = _latest_rows(conn)
        snapshot = conn.execute(
            """
            SELECT *
            FROM snapshots
            ORDER BY obs_time DESC, ingested_at DESC
            LIMIT 1
            """
        ).fetchone()

    stations: List[Dict[str, Any]] = []
    for row in rows:
        stations.append(
            {
                "station_id": row["station_id"],
                "station_name": row["station_name"],
                "county": row["county"],
                "town": row["town"],
                "lat": row["lat"],
                "lon": row["lon"],
                "altitude": row["altitude"],
                "obs_time": row["obs_time"],
                "weather": row["weather"],
                "temperature": row["temperature"],
                "humidity": row["humidity"],
                "pressure": row["pressure"],
                "wind_speed": row["wind_speed"],
                "wind_direction": row["wind_direction"],
                "gust_speed": row["gust_speed"],
                "precipitation": row["precipitation"],
                "uv_index": row["uv_index"],
                "color": row["color"],
                "category": row["category"],
                "has_temp": bool(row["has_temp"]),
            }
        )

    valid_temps = [s for s in stations if s["temperature"] is not None]
    valid_winds = [s for s in stations if s["wind_speed"] is not None]
    valid_rains = [s for s in stations if s["precipitation"] is not None]

    def extreme(items: List[Dict[str, Any]], key: str, fn):
        if not items:
            return {"value": None, "station_name": None, "county": None}
        item = fn(items, key=lambda s: s[key])
        return {
            "value": item[key],
            "station_name": item["station_name"],
            "county": item["county"],
        }

    avg_temp = (
        round(sum(s["temperature"] for s in valid_temps) / len(valid_temps), 1)
        if valid_temps else None
    )
    observation_time = max((s["obs_time"] for s in stations if s["obs_time"]), default=None)
    counties = sorted({s["county"] for s in stations if s["county"]})
    source_mode = rows[0]["source_mode"] if rows else "unknown"

    metadata: Dict[str, Any] = {
        "source": "CWA O-A0003-001 (氣象觀測站-10分鐘綜觀氣象資料)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observation_time": observation_time,
        "total_stations": len(stations),
        "valid_temp_stations": len(valid_temps),
        "stats": {
            "max_temperature": extreme(valid_temps, "temperature", max),
            "min_temperature": extreme(valid_temps, "temperature", min),
            "avg_temperature": avg_temp,
            "max_wind_speed": extreme(valid_winds, "wind_speed", max),
            "max_precipitation": extreme(valid_rains, "precipitation", max),
        },
        "counties": counties,
        "color_scale": COLOR_SCALE,
        "build_mode": source_mode,
        "storage": "sqlite",
    }

    if snapshot:
        try:
            snap_meta = json.loads(snapshot["metadata_json"])
            if snap_meta.get("source"):
                metadata["source"] = snap_meta["source"]
        except Exception:
            pass

    return {"metadata": metadata, "stations": stations}
