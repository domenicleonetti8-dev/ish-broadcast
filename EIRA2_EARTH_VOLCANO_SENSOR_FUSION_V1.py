from __future__ import annotations

import json, math, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "eira2_earth_volcano_sensor_fusion_v1"
ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
STATE = ROOT / "eira_probe" / "earth_observatory_v4" / "volcanoes"
STATE.mkdir(parents=True, exist_ok=True)
TIMEOUT = 20
MAX_ITEMS = 500
UA = "EIRA2-Earth-Volcano-Sensor-Fusion/1.0 (public-read-only; evidence-fusion)"

SOURCES = {
    "usgs_fdsn_station": {
        "endpoint": "https://earthquake.usgs.gov/fdsnws/station/1/query",
        "kind": "public_seismic_station_discovery",
        "live_sensor_data": False,
    },
    "usgs_fdsn_event": {
        "endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query",
        "kind": "earthquake_event_query",
        "live_sensor_data": False,
    },
    "usgs_vhp": {
        "url": "https://www.usgs.gov/programs/VHP",
        "kind": "official_volcano_hazards_reference",
        "live_sensor_feed": False,
    },
    "smithsonian_gvp": {
        "url": "https://volcano.si.edu/",
        "kind": "global_volcano_catalog_reference",
        "live_sensor_feed": False,
    },
    "earthscope": {
        "url": "https://www.earthscope.org/",
        "kind": "geodesy_and_seismic_reference",
        "live_sensor_feed": False,
    },
}


def _json(url: str, params: dict[str, Any]) -> Any:
    url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, application/geo+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _validate(lat: Any, lon: Any) -> tuple[float, float]:
    lat, lon = float(lat), float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("coordinates_must_be_finite")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("coordinates_out_of_range")
    return lat, lon


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(((b_lon - a_lon + 180) % 360) - 180)
    q = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(q)))


class VolcanoSensorFusion:
    def status(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "root": str(STATE),
            "sources": SOURCES,
            "policy": {
                "public_read_only": True,
                "source_is_not_fact": True,
                "no_fake_sensor_coverage": True,
                "no_claim_every_volcano_is_instrumented": True,
                "global_station_discovery": True,
                "seismicity_fusion": True,
                "deformation_gas_thermal_webcam_surfaces_registered": True,
                "sparse_monitoring_reported_explicitly": True,
            },
        }

    def seismic_stations_near(self, lat: float, lon: float, radius_km: float = 100.0, limit: int = 250) -> list[dict[str, Any]]:
        lat, lon = _validate(lat, lon)
        radius_km = max(1.0, min(float(radius_km), 1000.0))
        data = _json(SOURCES["usgs_fdsn_station"]["endpoint"], {
            "format": "geojson",
            "latitude": lat,
            "longitude": lon,
            "maxradiuskm": radius_km,
            "level": "station",
        })
        out = []
        for f in (data.get("features") or [])[:max(1, min(int(limit), MAX_ITEMS))]:
            g = f.get("geometry") or {}; c = g.get("coordinates") or []
            if len(c) < 2: continue
            try: slon, slat = float(c[0]), float(c[1])
            except Exception: continue
            p = f.get("properties") or {}
            out.append({
                "schema": SCHEMA,
                "sensor_type": "seismic_station",
                "sensor_id": f.get("id") or p.get("code") or "unknown",
                "network": p.get("network"),
                "station": p.get("station") or p.get("code"),
                "latitude": slat,
                "longitude": slon,
                "elevation_m": c[2] if len(c) > 2 else None,
                "distance_km": round(_haversine_km(lat, lon, slat, slon), 3),
                "source": "usgs_fdsn_station",
                "source_is_not_fact": True,
            })
        out.sort(key=lambda x: x["distance_km"])
        return out

    def earthquakes_near(self, lat: float, lon: float, radius_km: float = 100.0, min_magnitude: float = 0.0, limit: int = 250) -> list[dict[str, Any]]:
        lat, lon = _validate(lat, lon)
        params = {
            "format": "geojson",
            "latitude": lat,
            "longitude": lon,
            "maxradiuskm": max(1.0, min(float(radius_km), 2000.0)),
            "minmagnitude": float(min_magnitude),
            "limit": max(1, min(int(limit), MAX_ITEMS)),
            "orderby": "time",
        }
        data = _json(SOURCES["usgs_fdsn_event"]["endpoint"], params)
        out = []
        for f in data.get("features") or []:
            g = f.get("geometry") or {}; c = g.get("coordinates") or []
            p = f.get("properties") or {}
            if len(c) < 2: continue
            out.append({
                "schema": SCHEMA,
                "hazard": "volcanic_seismicity_candidate",
                "source_event_id": f.get("id"),
                "latitude": c[1],
                "longitude": c[0],
                "depth_km_below_surface": c[2] if len(c) > 2 else None,
                "magnitude": p.get("mag"),
                "place": p.get("place"),
                "observed_unix": (float(p.get("time")) / 1000.0) if p.get("time") is not None else None,
                "retrieved_unix": time.time(),
                "distance_km": round(_haversine_km(lat, lon, float(c[1]), float(c[0])), 3),
                "source": "usgs_fdsn_event",
                "source_is_not_fact": True,
            })
        return out

    def volcano_picture(self, name: str, lat: float, lon: float, radius_km: float = 100.0) -> dict[str, Any]:
        lat, lon = _validate(lat, lon)
        failures: dict[str, str] = {}
        try: stations = self.seismic_stations_near(lat, lon, radius_km)
        except Exception as e:
            stations = []; failures["stations"] = f"{type(e).__name__}:{e}"[:500]
        try: quakes = self.earthquakes_near(lat, lon, radius_km)
        except Exception as e:
            quakes = []; failures["earthquakes"] = f"{type(e).__name__}:{e}"[:500]
        coverage = "dense" if len(stations) >= 8 else "moderate" if len(stations) >= 3 else "sparse" if stations else "no_public_station_discovery"
        return {
            "schema": SCHEMA,
            "volcano": {"name": str(name), "latitude": lat, "longitude": lon},
            "radius_km": float(radius_km),
            "seismic_stations": stations,
            "recent_earthquakes": quakes,
            "monitoring_coverage": coverage,
            "reference_surfaces": {
                "usgs_vhp": SOURCES["usgs_vhp"],
                "smithsonian_gvp": SOURCES["smithsonian_gvp"],
                "earthscope": SOURCES["earthscope"],
                "deformation": "use public GNSS/InSAR when available",
                "gas": "use public SO2/CO2/ MultiGAS/remote-sensing feeds when available",
                "thermal": "use public satellite/thermal-camera products when available",
                "webcam": "use observatory webcams where public",
            },
            "rules": {
                "station_proximity_does_not_prove_volcanic_signal": True,
                "earthquake_proximity_does_not_prove_volcanic_origin": True,
                "absence_of_public_station_does_not_mean_unmonitored": True,
                "no_fake_sensor_assignment": True,
            },
            "failures": failures,
            "retrieved_unix": time.time(),
            "source_is_not_fact": True,
        }

    def global_volcano_sensor_contract(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "goal": "Every known volcano can be queried against nearby public sensors and evidence without inventing instrumentation.",
            "sensor_classes": ["seismic", "gnss_deformation", "insar_deformation", "gas", "thermal", "webcam", "infrasound", "satellite"],
            "coverage_rule": "discover what exists per volcano; explicitly report sparse or unavailable public coverage",
            "source_is_not_fact": True,
        }


def describe() -> dict[str, Any]:
    return VolcanoSensorFusion().status()

if __name__ == "__main__":
    print(json.dumps(describe(), indent=2, sort_keys=True))
