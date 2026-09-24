"""
Data normalization module for CWA O-A0003-001 (Automatic Weather Station 10-minute observation).
Gracefully handles missing data (-99, null, empty strings) and calculates summary statistics.
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple

SENTINEL_VALUES = {-99, -99.0, -999, -999.0, -9999, -9999.0}

# Temperature scale definitions
# Requirement: <10 blue, around 20-25 yellowish, >35 deep red
COLOR_SCALE_BINS: List[Tuple[Optional[float], Optional[float], str, str]] = [
    (None, 10.0, "#2563EB", "嚴寒 (<10°C)"),     # Deep Blue
    (10.0, 15.0, "#06B6D4", "寒冷 (10-15°C)"),           # Cyan
    (15.0, 20.0, "#10B981", "涼爽 (15-20°C)"),           # Green/Teal
    (20.0, 25.0, "#EAB308", "舒適 (20-25°C)"),           # Yellow-ish
    (25.0, 30.0, "#F97316", "溫暖 (25-30°C)"),           # Orange
    (30.0, 35.0, "#EF4444", "炎熱 (30-35°C)"),           # Red
    (35.0, None, "#991B1B", "酷熱 (>35°C)"),      # Deep Red
]

COLOR_NO_DATA = "#94A3B8"  # Slate gray for missing/invalid temperature


def clean_number(
    val: Any,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> Optional[float]:
    """Parse numeric values, gracefully filtering out CWA sentinel values (-99, etc.) and invalid types."""
    if val is None or val == "" or val == "None" or val == "null":
        return None
    try:
        num = float(val)
        if math.isnan(num) or math.isinf(num):
            return None
        if num in SENTINEL_VALUES:
            return None
        if min_val is not None and num < min_val:
            return None
        if max_val is not None and num > max_val:
            return None
        return round(num, 2)
    except (ValueError, TypeError):
        return None


def get_temperature_color_and_category(temp: Optional[float]) -> Tuple[str, str]:
    """
    Map temperature value to color hex and category name.
    Strictly adheres to:
      - < 10°C: blue
      - 20-25°C: yellowish
      - > 35°C: deep red
    """
    if temp is None:
        return COLOR_NO_DATA, "無資料"

    for lower, upper, color, category in COLOR_SCALE_BINS:
        if lower is None and upper is not None:
            if temp < upper:
                return color, category
        elif upper is None and lower is not None:
            if temp >= lower:
                return color, category
        elif lower is not None and upper is not None:
            if lower <= temp < upper:
                return color, category

    return COLOR_SCALE_BINS[-1][2], COLOR_SCALE_BINS[-1][3]


def extract_coordinates(geo_info: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Extract latitude and longitude from various CWA GeoInfo schemas."""
    if not isinstance(geo_info, dict):
        return None, None

    lat = None
    lon = None

    # Check direct fields
    if "StationLatitude" in geo_info:
        lat = clean_number(geo_info.get("StationLatitude"), min_val=15.0, max_val=30.0)
    if "StationLongitude" in geo_info:
        lon = clean_number(geo_info.get("StationLongitude"), min_val=115.0, max_val=125.0)

    # Check Coordinates array
    coords = geo_info.get("Coordinates")
    if (lat is None or lon is None) and isinstance(coords, list) and len(coords) > 0:
        c0 = coords[0]
        if isinstance(c0, dict):
            if lat is None:
                lat = clean_number(c0.get("StationLatitude"), min_val=15.0, max_val=30.0)
            if lon is None:
                lon = clean_number(c0.get("StationLongitude"), min_val=115.0, max_val=125.0)

    if lat is None or lon is None:
        return None, None
    return lat, lon


def extract_weather_elements(station: Dict[str, Any]) -> Dict[str, Any]:
    """Extract weather elements whether they are formatted as a dict or a list."""
    we = station.get("WeatherElement") or station.get("weatherElement") or {}
    elements: Dict[str, Any] = {}

    if isinstance(we, dict):
        elements = we
    elif isinstance(we, list):
        # Legacy CWA format: [{"elementName": "TEMP", "elementValue": "25.0"}, ...]
        for item in we:
            if isinstance(item, dict):
                name = item.get("elementName") or item.get("ElementName")
                val = item.get("elementValue") or item.get("ElementValue")
                if name:
                    elements[name] = val

    return elements


def normalize_station(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a single raw station record into a clean frontend schema."""
    if not isinstance(raw, dict):
        return None

    station_id = str(raw.get("StationId") or raw.get("stationId") or "").strip()
    station_name = str(raw.get("StationName") or raw.get("stationName") or "").strip()

    geo = raw.get("GeoInfo") or raw.get("geoInfo") or {}
    lat, lon = extract_coordinates(geo)

    # If coordinates are missing or invalid, station cannot be rendered on map
    if lat is None or lon is None:
        return None

    county = str(geo.get("CountyName") or raw.get("County") or raw.get("county") or "其他").strip()
    town = str(geo.get("TownName") or raw.get("Town") or raw.get("town") or "").strip()
    altitude = clean_number(geo.get("StationAltitude") or raw.get("StationAltitude"))

    # Observation time
    obs_time_obj = raw.get("ObsTime") or raw.get("obsTime") or {}
    if isinstance(obs_time_obj, dict):
        obs_time = obs_time_obj.get("DateTime") or obs_time_obj.get("dateTime")
    else:
        obs_time = str(obs_time_obj) if obs_time_obj else None

    # Weather elements
    we = extract_weather_elements(raw)

    weather_desc = str(
        we.get("Weather")
        or we.get("WeatherDescription")
        or we.get("weather")
        or "晴"
    ).strip()

    # Temperature
    raw_temp = we.get("AirTemperature") or we.get("TEMP") or we.get("temperature")
    temp = clean_number(raw_temp, min_val=-40.0, max_val=60.0)

    # Humidity (0 - 100%)
    raw_hum = we.get("RelativeHumidity") or we.get("HUMD") or we.get("humidity")
    humidity = clean_number(raw_hum, min_val=0.0, max_val=100.0)

    # Pressure (hPa)
    raw_press = we.get("AirPressure") or we.get("PRES") or we.get("pressure")
    pressure = clean_number(raw_press, min_val=500.0, max_val=1100.0)

    # Wind Speed (m/s)
    raw_ws = we.get("WindSpeed") or we.get("WDIR_SPEED") or we.get("windSpeed")
    wind_speed = clean_number(raw_ws, min_val=0.0, max_val=120.0)

    # Wind Direction (deg)
    raw_wd = we.get("WindDirection") or we.get("WDIR") or we.get("windDirection")
    wind_direction = clean_number(raw_wd, min_val=0.0, max_val=360.0)

    # Peak Gust Speed (m/s)
    raw_gust = we.get("PeakGustSpeed") or we.get("gustSpeed")
    gust_speed = clean_number(raw_gust, min_val=0.0, max_val=120.0)

    # Precipitation (mm)
    raw_rain = (
        we.get("Precipitation")
        or we.get("RAIN")
        or we.get("Now")
        or we.get("precipitation")
    )
    precipitation = clean_number(raw_rain, min_val=0.0, max_val=2000.0)

    # UV Index
    raw_uvi = we.get("UVIndex") or we.get("UVI") or we.get("uvi")
    uv_index = clean_number(raw_uvi, min_val=0.0, max_val=25.0)

    color, category = get_temperature_color_and_category(temp)

    return {
        "station_id": station_id,
        "station_name": station_name,
        "county": county,
        "town": town,
        "lat": lat,
        "lon": lon,
        "altitude": altitude,
        "obs_time": obs_time,
        "weather": weather_desc,
        "temperature": temp,
        "humidity": humidity,
        "pressure": pressure,
        "wind_speed": wind_speed,
        "wind_direction": wind_direction,
        "gust_speed": gust_speed,
        "precipitation": precipitation,
        "uv_index": uv_index,
        "color": color,
        "category": category,
        "has_temp": temp is not None,
    }


def normalize_cwa_dataset(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms CWA O-A0003-001 payload into the unified frontend schema with summary metrics.
    """
    records = raw_data.get("records") or raw_data.get("Records") or {}
    raw_stations = records.get("Station") or records.get("station") or records.get("location") or []

    # If raw_data itself is a list or already contains feature collection
    if isinstance(raw_data.get("features"), list):
        # GeoJSON input conversion
        return normalize_geojson_dataset(raw_data)

    stations: List[Dict[str, Any]] = []
    for item in raw_stations:
        st = normalize_station(item)
        if st is not None:
            stations.append(st)

    # Sort stations: valid temperatures first (descending by temperature), then alphabetically
    stations.sort(
        key=lambda s: (
            0 if s["temperature"] is not None else 1,
            -(s["temperature"] if s["temperature"] is not None else -999),
            s["county"],
            s["station_name"],
        )
    )

    # Calculate aggregate metrics
    valid_temps = [s for s in stations if s["temperature"] is not None]
    valid_winds = [s for s in stations if s["wind_speed"] is not None]
    valid_rains = [s for s in stations if s["precipitation"] is not None]

    max_temp_st = (
        max(valid_temps, key=lambda s: s["temperature"]) if valid_temps else None
    )
    min_temp_st = (
        min(valid_temps, key=lambda s: s["temperature"]) if valid_temps else None
    )
    max_wind_st = (
        max(valid_winds, key=lambda s: s["wind_speed"]) if valid_winds else None
    )
    max_rain_st = (
        max(valid_rains, key=lambda s: s["precipitation"]) if valid_rains else None
    )

    avg_temp = (
        round(sum(s["temperature"] for s in valid_temps) / len(valid_temps), 1)
        if valid_temps
        else None
    )

    # Find primary observation time
    obs_times = [s["obs_time"] for s in stations if s.get("obs_time")]
    primary_obs_time = obs_times[0] if obs_times else datetime.now(timezone.utc).isoformat()

    counties = sorted(list(set(s["county"] for s in stations if s["county"])))

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "metadata": {
            "source": "CWA O-A0003-001 (氣象觀測站-10分鐘綜觀氣象資料)",
            "generated_at": now_iso,
            "observation_time": primary_obs_time,
            "total_stations": len(stations),
            "valid_temp_stations": len(valid_temps),
            "stats": {
                "max_temperature": {
                    "value": max_temp_st["temperature"] if max_temp_st else None,
                    "station_name": max_temp_st["station_name"] if max_temp_st else None,
                    "county": max_temp_st["county"] if max_temp_st else None,
                },
                "min_temperature": {
                    "value": min_temp_st["temperature"] if min_temp_st else None,
                    "station_name": min_temp_st["station_name"] if min_temp_st else None,
                    "county": min_temp_st["county"] if min_temp_st else None,
                },
                "avg_temperature": avg_temp,
                "max_wind_speed": {
                    "value": max_wind_st["wind_speed"] if max_wind_st else None,
                    "station_name": max_wind_st["station_name"] if max_wind_st else None,
                    "county": max_wind_st["county"] if max_wind_st else None,
                },
                "max_precipitation": {
                    "value": max_rain_st["precipitation"] if max_rain_st else None,
                    "station_name": max_rain_st["station_name"] if max_rain_st else None,
                    "county": max_rain_st["county"] if max_rain_st else None,
                },
            },
            "counties": counties,
            "color_scale": [
                {"min": b[0], "max": b[1], "color": b[2], "label": b[3]}
                for b in COLOR_SCALE_BINS
            ],
        },
        "stations": stations,
    }


def normalize_geojson_dataset(geo_data: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to convert GeoJSON FeatureCollection if provided as source."""
    features = geo_data.get("features", [])
    raw_stations = []
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        raw_stations.append({
            "StationId": props.get("stationId"),
            "StationName": props.get("stationName"),
            "GeoInfo": {
                "CountyName": props.get("county"),
                "TownName": props.get("town"),
                "Coordinates": [
                    {
                        "StationLongitude": coords[0],
                        "StationLatitude": coords[1],
                    }
                ],
            },
            "ObsTime": {"DateTime": props.get("observedAt")},
            "WeatherElement": {
                "AirTemperature": props.get("temperature"),
                "RelativeHumidity": props.get("humidity"),
                "AirPressure": props.get("pressure"),
                "WindSpeed": props.get("windSpeed"),
                "WindDirection": props.get("windDirection"),
                "PeakGustSpeed": props.get("gustSpeed"),
                "Precipitation": props.get("precipitation"),
                "UVIndex": props.get("uvi"),
                "Weather": props.get("weather"),
            },
        })

    return normalize_cwa_dataset({"records": {"Station": raw_stations}})


FORECAST_COURSE_REGIONS: List[str] = [
    "北部地區",
    "中部地區",
    "南部地區",
    "東北部地區",
    "東部地區",
    "東南部地區",
]


def normalize_forecast_dataset(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms CWA forecast payloads into normalized 7-day regional forecast data.
    Supports both:
      - Current official F-C0032-003 ("一般天氣預報-七天天氣預報")
      - Course legacy F-A0010-001 ("一週農業氣象預報") as compatibility parser/reference
    Output:
      - Six course regions: 北部地區, 中部地區, 南部地區, 東北部地區, 東部地區, 東南部地區
      - 7-day rows per region
      - fields: regionName, dataDate, mint, maxt
    """
    region_rows: Dict[str, List[Dict[str, Any]]] = {}
    source_dataset = "F-A0010-001"
    source_title = "CWA F-A0010-001 (一週農業氣象預報)"

    cwa = raw_data.get("cwaopendata", {}) if isinstance(raw_data, dict) else {}
    data_id = str(
        cwa.get("Dataid")
        or cwa.get("dataid")
        or raw_data.get("Dataid")
        or raw_data.get("dataid")
        or ""
    )
    is_c0032 = (
        "C0032-003" in data_id
        or ("Dataset" in cwa and "Locations" in cwa.get("Dataset", {}))
        or ("Dataset" in raw_data and "Locations" in raw_data.get("Dataset", {}))
    )

    if is_c0032:
        source_dataset = "F-C0032-003"
        source_title = "CWA F-C0032-003 (一般天氣預報-七天天氣預報)"
        dataset_obj = cwa.get("Dataset") or raw_data.get("Dataset") or {}
        loc_list = dataset_obj.get("Locations", {}).get("Location", [])

        for loc in loc_list:
            if not isinstance(loc, dict):
                continue
            reg_name = str(loc.get("LocationName") or "").strip()
            if reg_name not in FORECAST_COURSE_REGIONS:
                continue

            we_elements = loc.get("WeatherElement", [])
            maxt_by_date: Dict[str, Optional[float]] = {}
            mint_by_date: Dict[str, Optional[float]] = {}

            for elem in we_elements:
                elem_name = str(elem.get("ElementName") or "").strip()
                time_list = elem.get("Time", [])
                if elem_name == "最高溫度":
                    for t in time_list:
                        dt = str(t.get("StartTime", ""))[:10].strip()
                        val = clean_number(t.get("ElementValue", {}).get("MaxTemperature"))
                        if dt:
                            maxt_by_date[dt] = val
                elif elem_name == "最低溫度":
                    for t in time_list:
                        dt = str(t.get("StartTime", ""))[:10].strip()
                        val = clean_number(t.get("ElementValue", {}).get("MinTemperature"))
                        if dt:
                            mint_by_date[dt] = val

            all_dates = sorted(set(maxt_by_date.keys()) | set(mint_by_date.keys()))
            rows_for_region: List[Dict[str, Any]] = []
            for dt in all_dates:
                rows_for_region.append({
                    "regionName": reg_name,
                    "dataDate": dt,
                    "mint": mint_by_date.get(dt),
                    "maxt": maxt_by_date.get(dt),
                })
            region_rows[reg_name] = rows_for_region
    else:
        # Legacy F-A0010-001 parser
        source_dataset = "F-A0010-001"
        source_title = "CWA F-A0010-001 (一週農業氣象預報)"
        locations: List[Dict[str, Any]] = []

        if isinstance(raw_data, dict):
            if "cwaopendata" in raw_data:
                res = raw_data["cwaopendata"].get("resources", {}).get("resource", {})
                if isinstance(res, list):
                    res = res[0] if res else {}
                locations = (
                    res.get("data", {})
                    .get("agrWeatherForecasts", {})
                    .get("weatherForecasts", {})
                    .get("location", [])
                )
            elif "records" in raw_data:
                rec = raw_data["records"]
                if "resources" in rec:
                    res = rec.get("resources", {}).get("resource", {})
                    if isinstance(res, list):
                        res = res[0] if res else {}
                    locations = (
                        res.get("data", {})
                        .get("agrWeatherForecasts", {})
                        .get("weatherForecasts", {})
                        .get("location", [])
                    )
                elif "agrWeatherForecasts" in rec:
                    locations = (
                        rec.get("agrWeatherForecasts", {})
                        .get("weatherForecasts", {})
                        .get("location", [])
                    )
                elif "weatherForecasts" in rec:
                    locations = rec.get("weatherForecasts", {}).get("location", [])
                elif "location" in rec:
                    locations = rec.get("location", [])
            elif "agrWeatherForecasts" in raw_data:
                locations = (
                    raw_data.get("agrWeatherForecasts", {})
                    .get("weatherForecasts", {})
                    .get("location", [])
                )
            elif "weatherForecasts" in raw_data:
                locations = raw_data.get("weatherForecasts", {}).get("location", [])
            elif "location" in raw_data:
                locations = raw_data.get("location", [])

        if not locations and isinstance(raw_data, dict):
            def _find_locations(node: Any) -> List[Dict[str, Any]]:
                if isinstance(node, dict):
                    if "location" in node and isinstance(node["location"], list):
                        return node["location"]
                    for val in node.values():
                        found = _find_locations(val)
                        if found:
                            return found
                return []
            locations = _find_locations(raw_data)

        for loc in locations:
            if not isinstance(loc, dict):
                continue
            reg_name = str(
                loc.get("locationName")
                or loc.get("location_name")
                or loc.get("regionName")
                or ""
            ).strip()
            if not reg_name:
                continue

            we = loc.get("weatherElements") or loc.get("weatherElement") or {}
            if isinstance(we, list):
                we_map: Dict[str, Any] = {}
                for item in we:
                    if isinstance(item, dict):
                        name = item.get("elementName") or item.get("tagName") or item.get("name")
                        if name:
                            we_map[name] = item
                we = we_map

            mint_obj = we.get("MinT") or we.get("minT") or we.get("mint") or {}
            maxt_obj = we.get("MaxT") or we.get("maxT") or we.get("maxt") or {}

            mint_daily = mint_obj.get("daily", []) if isinstance(mint_obj, dict) else []
            maxt_daily = maxt_obj.get("daily", []) if isinstance(maxt_obj, dict) else []

            mint_by_date: Dict[str, Optional[float]] = {}
            for d in mint_daily:
                if isinstance(d, dict) and "dataDate" in d:
                    dt = str(d["dataDate"]).strip()
                    mint_by_date[dt] = clean_number(d.get("temperature"))

            maxt_by_date: Dict[str, Optional[float]] = {}
            for d in maxt_daily:
                if isinstance(d, dict) and "dataDate" in d:
                    dt = str(d["dataDate"]).strip()
                    maxt_by_date[dt] = clean_number(d.get("temperature"))

            all_dates = sorted(set(mint_by_date.keys()) | set(maxt_by_date.keys()))
            rows_for_region: List[Dict[str, Any]] = []
            for dt in all_dates:
                rows_for_region.append({
                    "regionName": reg_name,
                    "dataDate": dt,
                    "mint": mint_by_date.get(dt),
                    "maxt": maxt_by_date.get(dt),
                })
            region_rows[reg_name] = rows_for_region

    # Order regions according to the six course regions
    ordered_course = [r for r in FORECAST_COURSE_REGIONS if r in region_rows]
    extra = sorted([r for r in region_rows if r not in FORECAST_COURSE_REGIONS])
    final_regions = ordered_course + extra

    all_rows: List[Dict[str, Any]] = []
    for reg in final_regions:
        all_rows.extend(region_rows[reg])

    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "metadata": {
            "source": source_title,
            "source_dataset": source_dataset,
            "generated_at": now_iso,
            "total_regions": len(final_regions),
            "total_records": len(all_rows),
            "regions": final_regions,
            "build_mode": "normalized",
        },
        "regions": final_regions,
        "forecasts": all_rows,
        "rows": all_rows,
    }

