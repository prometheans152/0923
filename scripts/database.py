"""SQLite persistence module for Taiwan CWA Weather Station Dashboard.

Gate 2 requires fetched CWA observations to be persisted in SQLite and queryable.
Never stores or logs secrets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
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
    """Connect to SQLite database with standard read-write permissions."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def connect_readonly(db_path: Path | str) -> sqlite3.Connection:
    """Connect to SQLite database in read-only mode where supported."""
    path = Path(db_path).resolve()
    if not path.is_file():
        return connect(path)
    uri_path = f"file:{path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri_path, uri=True)
    except Exception:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str) -> None:
    """Initialize SQLite tables: metadata, observations, snapshots, and TemperatureForecasts."""
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                source TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                observation_time TEXT NOT NULL,
                total_stations INTEGER NOT NULL,
                valid_temp_stations INTEGER NOT NULL,
                build_mode TEXT NOT NULL,
                stats_json TEXT,
                counties_json TEXT,
                color_scale_json TEXT
            );

            CREATE TABLE IF NOT EXISTS observations (
                station_id TEXT PRIMARY KEY,
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
                ingested_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_observations_county
                ON observations(county);
            CREATE INDEX IF NOT EXISTS idx_observations_obs_time
                ON observations(obs_time);
            CREATE INDEX IF NOT EXISTS idx_observations_temperature
                ON observations(temperature);

            CREATE TABLE IF NOT EXISTS snapshots (
                obs_time TEXT NOT NULL,
                source_mode TEXT NOT NULL,
                generated_at TEXT,
                station_count INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (obs_time, source_mode)
            );

            CREATE TABLE IF NOT EXISTS TemperatureForecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regionName TEXT NOT NULL,
                dataDate TEXT NOT NULL,
                mint REAL,
                maxt REAL,
                UNIQUE(regionName, dataDate)
            );

            CREATE INDEX IF NOT EXISTS idx_forecasts_region
                ON TemperatureForecasts(regionName);

            CREATE TABLE IF NOT EXISTS forecast_metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                source TEXT NOT NULL,
                source_dataset TEXT NOT NULL,
                build_mode TEXT NOT NULL,
                generated_at TEXT
            );
            """
        )


def upsert_payload(
    db_path: Path | str,
    payload: Dict[str, Any],
    source_mode: Optional[str] = None,
    replace: bool = True,
) -> int:
    """
    Persist normalized CWA payload into SQLite atomically.
    When replace=True, replaces the current snapshot in a single transaction.
    """
    init_db(db_path)
    metadata = payload.get("metadata") or {}
    mode = source_mode or metadata.get("build_mode") or "unknown"
    gen_at = metadata.get("generated_at") or ""
    obs_time = str(metadata.get("observation_time") or "").strip()
    stations = payload.get("stations") or []

    rows = []
    for st in stations:
        station_id = str(st.get("station_id") or "").strip()
        st_obs = str(st.get("obs_time") or obs_time).strip()
        if not station_id:
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
                st_obs,
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
                gen_at,
            )
        )

    with connect(db_path) as conn:
        if replace:
            conn.execute("DELETE FROM observations")
            conn.execute("DELETE FROM metadata")

        conn.executemany(
            """
            INSERT OR REPLACE INTO observations (
                station_id, station_name, county, town, lat, lon, altitude,
                obs_time, weather, temperature, humidity, pressure, wind_speed,
                wind_direction, gust_speed, precipitation, uv_index, color,
                category, has_temp, source_mode, ingested_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )

        valid_temp_count = sum(1 for r in rows if r[9] is not None)
        conn.execute(
            """
            INSERT OR REPLACE INTO metadata (
                id, source, generated_at, observation_time, total_stations,
                valid_temp_stations, build_mode, stats_json, counties_json, color_scale_json
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata.get("source") or "CWA O-A0003-001 (氣象觀測站-10分鐘綜觀氣象資料)",
                gen_at,
                obs_time,
                len(rows),
                valid_temp_count,
                mode,
                json.dumps(metadata.get("stats") or {}, ensure_ascii=False),
                json.dumps(metadata.get("counties") or [], ensure_ascii=False),
                json.dumps(metadata.get("color_scale") or COLOR_SCALE, ensure_ascii=False),
            ),
        )

        if obs_time:
            conn.execute(
                """
                INSERT OR REPLACE INTO snapshots (
                    obs_time, source_mode, generated_at, station_count,
                    metadata_json, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    obs_time,
                    mode,
                    gen_at,
                    len(rows),
                    json.dumps(metadata, ensure_ascii=False),
                    gen_at,
                ),
            )
    return len(rows)


def row_count(db_path: Path | str) -> int:
    """Return the total number of stations in the SQLite database."""
    init_db(db_path)
    with connect_readonly(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0])


def latest_observation_time(db_path: Path | str) -> Optional[str]:
    """Return the primary observation timestamp recorded in metadata or observations."""
    init_db(db_path)
    with connect_readonly(db_path) as conn:
        meta_row = conn.execute("SELECT observation_time FROM metadata WHERE id = 1").fetchone()
        if meta_row and meta_row["observation_time"]:
            return meta_row["observation_time"]
        row = conn.execute("SELECT MAX(obs_time) AS obs_time FROM observations").fetchone()
        return row["obs_time"] if row and row["obs_time"] else None


def query_sample(
    db_path: Path | str,
    county: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Query a sample of weather observation rows safely for inspection."""
    init_db(db_path)
    limit = max(1, min(int(limit), 50))
    with connect_readonly(db_path) as conn:
        if county:
            rows = conn.execute(
                """
                SELECT station_id, station_name, county, town, lat, lon,
                       obs_time, weather, temperature, humidity, wind_speed, precipitation
                FROM observations
                WHERE county = ?
                ORDER BY station_name
                LIMIT ?
                """,
                (county, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT station_id, station_name, county, town, lat, lon,
                       obs_time, weather, temperature, humidity, wind_speed, precipitation
                FROM observations
                ORDER BY station_name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def payload_from_db(db_path: Path | str) -> Dict[str, Any]:
    """Reconstruct the complete frontend payload directly from SQLite."""
    init_db(db_path)
    with connect_readonly(db_path) as conn:
        meta_row = conn.execute("SELECT * FROM metadata WHERE id = 1").fetchone()
        obs_rows = conn.execute(
            """
            SELECT * FROM observations
            ORDER BY
                has_temp DESC,
                CASE WHEN temperature IS NULL THEN -999 ELSE temperature END DESC,
                county,
                station_name
            """
        ).fetchall()

    stations: List[Dict[str, Any]] = []
    for row in obs_rows:
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

    stats = {
        "max_temperature": extreme(valid_temps, "temperature", max),
        "min_temperature": extreme(valid_temps, "temperature", min),
        "avg_temperature": (
            round(sum(s["temperature"] for s in valid_temps) / len(valid_temps), 1)
            if valid_temps else None
        ),
        "max_wind_speed": extreme(valid_winds, "wind_speed", max),
        "max_precipitation": extreme(valid_rains, "precipitation", max),
    }

    counties = sorted({s["county"] for s in stations if s["county"]})
    obs_time = (
        meta_row["observation_time"]
        if meta_row and meta_row["observation_time"]
        else (stations[0]["obs_time"] if stations else "")
    )
    gen_at = (
        meta_row["generated_at"]
        if meta_row and meta_row["generated_at"]
        else ""
    )
    source = (
        meta_row["source"]
        if meta_row and meta_row["source"]
        else "CWA O-A0003-001 (氣象觀測站-10分鐘綜觀氣象資料)"
    )
    build_mode = (
        meta_row["build_mode"]
        if meta_row and meta_row["build_mode"]
        else (obs_rows[0]["source_mode"] if obs_rows else "sqlite")
    )

    if meta_row and meta_row["stats_json"]:
        try:
            loaded_stats = json.loads(meta_row["stats_json"])
            if loaded_stats:
                stats = loaded_stats
        except Exception:
            pass

    if meta_row and meta_row["counties_json"]:
        try:
            loaded_counties = json.loads(meta_row["counties_json"])
            if loaded_counties:
                counties = loaded_counties
        except Exception:
            pass

    color_scale = COLOR_SCALE
    if meta_row and meta_row["color_scale_json"]:
        try:
            loaded_scale = json.loads(meta_row["color_scale_json"])
            if loaded_scale:
                color_scale = loaded_scale
        except Exception:
            pass

    metadata = {
        "source": source,
        "generated_at": gen_at,
        "observation_time": obs_time,
        "total_stations": len(stations),
        "valid_temp_stations": len(valid_temps),
        "stats": stats,
        "counties": counties,
        "color_scale": color_scale,
        "build_mode": build_mode,
        "storage": "sqlite",
    }

    return {"metadata": metadata, "stations": stations}


COURSE_REGIONS: List[str] = [
    "北部地區",
    "中部地區",
    "南部地區",
    "東北部地區",
    "東部地區",
    "東南部地區",
]


def upsert_forecast_rows(
    db_path: Path | str,
    rows: List[Dict[str, Any]],
    replace: bool = False,
) -> int:
    """
    Persist normalized forecast rows into TemperatureForecasts table.
    When replace=True, removes existing forecast records.
    Uses UNIQUE(regionName, dataDate) to update existing rows on conflict.
    """
    init_db(db_path)
    tuples = []
    for r in rows:
        reg = str(r.get("regionName") or "").strip()
        dt = str(r.get("dataDate") or "").strip()
        if not reg or not dt:
            continue
        tuples.append((reg, dt, r.get("mint"), r.get("maxt")))

    with connect(db_path) as conn:
        if replace:
            conn.execute("DELETE FROM TemperatureForecasts")
        conn.executemany(
            """
            INSERT INTO TemperatureForecasts (regionName, dataDate, mint, maxt)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(regionName, dataDate) DO UPDATE SET
                mint = excluded.mint,
                maxt = excluded.maxt
            """,
            tuples,
        )
    return len(tuples)


def upsert_forecast_payload(
    db_path: Path | str,
    payload: Dict[str, Any],
    replace: bool = False,
) -> int:
    """Persist a normalized forecast payload dictionary into SQLite."""
    init_db(db_path)
    rows = payload.get("forecasts") or payload.get("rows") or []
    count = upsert_forecast_rows(db_path, rows, replace=replace)

    metadata = payload.get("metadata") or {}
    source = metadata.get("source") or "CWA F-C0032-003 (一般天氣預報-七天天氣預報)"
    source_dataset = metadata.get("source_dataset") or "F-C0032-003"
    build_mode = metadata.get("build_mode") or "live_cwa_api"
    gen_at = metadata.get("generated_at") or ""

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO forecast_metadata (id, source, source_dataset, build_mode, generated_at)
            VALUES (1, ?, ?, ?, ?)
            """,
            (source, source_dataset, build_mode, gen_at),
        )
    return count


def forecast_row_count(db_path: Path | str) -> int:
    """Return total number of rows in TemperatureForecasts table."""
    init_db(db_path)
    with connect_readonly(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM TemperatureForecasts").fetchone()
        return int(row[0]) if row else 0


def list_forecast_regions(db_path: Path | str) -> List[str]:
    """Return distinct region names present in TemperatureForecasts, in course order."""
    init_db(db_path)
    with connect_readonly(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT regionName FROM TemperatureForecasts"
        ).fetchall()
    found = [r["regionName"] for r in rows if r["regionName"]]
    return sorted(
        found,
        key=lambda name: COURSE_REGIONS.index(name) if name in COURSE_REGIONS else 999,
    )


def query_forecast_rows(
    db_path: Path | str,
    region: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query forecast rows, optionally filtered by regionName."""
    init_db(db_path)
    with connect_readonly(db_path) as conn:
        if region:
            db_rows = conn.execute(
                """
                SELECT id, regionName, dataDate, mint, maxt
                FROM TemperatureForecasts
                WHERE regionName = ?
                ORDER BY dataDate ASC
                """,
                (region,),
            ).fetchall()
        else:
            db_rows = conn.execute(
                """
                SELECT id, regionName, dataDate, mint, maxt
                FROM TemperatureForecasts
                ORDER BY regionName ASC, dataDate ASC
                """
            ).fetchall()

    results = [
        {
            "id": r["id"],
            "regionName": r["regionName"],
            "dataDate": r["dataDate"],
            "mint": r["mint"],
            "maxt": r["maxt"],
        }
        for r in db_rows
    ]
    if not region:
        results.sort(
            key=lambda item: (
                COURSE_REGIONS.index(item["regionName"])
                if item["regionName"] in COURSE_REGIONS
                else 999,
                item["dataDate"],
            )
        )
    return results


def forecast_payload_from_db(
    db_path: Path | str,
    region: Optional[str] = None,
) -> Dict[str, Any]:
    """Reconstruct complete forecast payload directly from SQLite."""
    init_db(db_path)
    regions = list_forecast_regions(db_path)
    rows = query_forecast_rows(db_path, region=region)

    source = "CWA F-C0032-003 (一般天氣預報-七天天氣預報)"
    source_dataset = "F-C0032-003"
    build_mode = "sqlite"
    gen_at = ""

    with connect_readonly(db_path) as conn:
        meta_row = conn.execute(
            "SELECT * FROM forecast_metadata WHERE id = 1"
        ).fetchone()
        if meta_row:
            source = meta_row["source"] or source
            source_dataset = meta_row["source_dataset"] or source_dataset
            build_mode = meta_row["build_mode"] or build_mode
            gen_at = meta_row["generated_at"] or ""

    return {
        "metadata": {
            "source": source,
            "source_dataset": source_dataset,
            "build_mode": build_mode,
            "generated_at": gen_at,
            "region": region,
            "regions": regions,
            "total_records": len(rows),
            "storage": "sqlite",
        },
        "region": region,
        "regions": regions,
        "forecasts": rows,
        "rows": rows,
    }


def verify_database(db_path: Path | str, county: str = "新竹縣", limit: int = 3) -> None:
    """Print non-secret verification details for Gate 2 inspection."""
    path = Path(db_path)
    if not path.is_file():
        print(f"[ERROR] Database file not found at: {path}")
        return

    count = row_count(path)
    obs_time = latest_observation_time(path)
    payload = payload_from_db(path)
    meta = payload.get("metadata", {})
    mode = meta.get("build_mode", "unknown")

    print(f"=== SQLite Verification ({path.name}) ===")
    print(f"Total stations (COUNT): {count}")
    print(f"Observation time:       {obs_time}")
    print(f"Build mode:             {mode}")
    print(f"Storage backend:        {meta.get('storage')}")

    samples = query_sample(path, county=county, limit=limit)
    if not samples:
        samples = query_sample(path, county=None, limit=limit)

    print(f"\nSample query ({county if samples else 'All'}, {len(samples)} rows):")
    for s in samples:
        t_str = f"{s['temperature']}°C" if s['temperature'] is not None else "--"
        h_str = f"{s['humidity']}%" if s['humidity'] is not None else "--"
        w_str = f"{s['wind_speed']} m/s" if s['wind_speed'] is not None else "--"
        print(
            f"  - {s['station_name']} ({s['station_id']}) [{s['county']} {s['town'] or ''}]: "
            f"Temp: {t_str}, RH: {h_str}, Wind: {w_str}, Weather: {s['weather'] or '--'}"
        )


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Query and verify SQLite weather observations")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data.db",
        help="Path to data.db",
    )
    parser.add_argument("--county", type=str, default="新竹縣", help="County to filter for sample")
    parser.add_argument("--limit", type=int, default=3, help="Max sample rows to display")
    args = parser.parse_args()
    verify_database(args.db, county=args.county, limit=args.limit)


if __name__ == "__main__":
    main_cli()
