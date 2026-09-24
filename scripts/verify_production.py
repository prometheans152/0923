"""Verify public production endpoints on Vercel and GitHub Pages safely."""
import json
import urllib.request

VERCEL_BASE = "https://0923-site.vercel.app"
PAGES_BASE = "https://prometheans152.github.io/0923"


def check_vercel():
    print("=== VERCEL PRODUCTION VERIFICATION ===")
    routes = ["/", "/app.js", "/data/stations.json", "/api/weather", "/api/db-check"]
    for r in routes:
        url = VERCEL_BASE + r
        resp = urllib.request.urlopen(url, timeout=15)
        print(f"  GET {r:22s} -> HTTP {resp.status}")

    w_req = urllib.request.urlopen(VERCEL_BASE + "/api/weather", timeout=15)
    w_data = json.loads(w_req.read().decode("utf-8"))
    meta = w_data.get("metadata", {})
    stations = w_data.get("stations", [])
    print("\n  /api/weather contract:")
    print(f"    - storage:          {meta.get('storage')}")
    print(f"    - build_mode:       {meta.get('build_mode')}")
    print(f"    - observation_time: {meta.get('observation_time')}")
    print(f"    - stations count:   {len(stations)}")

    db_req = urllib.request.urlopen(
        VERCEL_BASE + "/api/db-check?county=%E6%96%B0%E7%AB%B9%E7%B8%A3&limit=3",
        timeout=15,
    )
    d_data = json.loads(db_req.read().decode("utf-8"))
    print("\n  /api/db-check proof:")
    print(f"    - database:         {d_data.get('database')}")
    print(f"    - row_count:        {d_data.get('row_count')}")
    print(f"    - latest_obs:       {d_data.get('latest_observation_time')}")
    print("    - sample rows:")
    for s in d_data.get("sample", []):
        print(
            f"      * {s['station_name']} ({s['station_id']}) "
            f"[{s['county']} {s['town']}]: Temp {s['temperature']}°C, "
            f"RH {s['humidity']}%, Wind {s['wind_speed']} m/s, Weather: {s['weather']}"
        )


def check_github_pages():
    print("\n=== GITHUB PAGES FALLBACK VERIFICATION ===")
    routes = ["/", "/data/stations.json"]
    for r in routes:
        url = PAGES_BASE + r
        try:
            resp = urllib.request.urlopen(url, timeout=15)
            print(f"  GET {r:22s} -> HTTP {resp.status}")
        except Exception as exc:
            print(f"  GET {r:22s} -> FAILED ({exc})")


if __name__ == "__main__":
    check_vercel()
    check_github_pages()
