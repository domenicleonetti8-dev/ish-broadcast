from __future__ import annotations

import json, math, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "eira2_earth_volcano_sensor_fusion_v2"
ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
STATE = ROOT / "eira_probe" / "earth_observatory_v4" / "volcanoes"
STATE.mkdir(parents=True, exist_ok=True)
TIMEOUT = 20
MAX_ITEMS = 500
UA = "EIRA2-Earth-Volcano-Sensor-Fusion/2.0 (public-read-only; evidence-fusion)"

SOURCES = {
    "earthscope_fdsn_station": {
        "endpoint": "https://service.earthscope.org/fdsnws/station/1/query",
        "kind": "public_seismic_station_metadata",
        "format": "text",
        "radius_unit": "degrees",
        "live_sensor_data": False,
    },
    "earthscope_fdsn_dataselect": {
        "endpoint": "https://service.earthscope.org/fdsnws/dataselect/1/query",
        "kind": "public_seismic_waveform_surface",
        "automatic_waveform_download": False,
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


def _urlopen(url: str, params: dict[str, Any], accept: str) -> bytes:
    url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _json(url: str, params: dict[str, Any]) -> Any:
    return json.loads(_urlopen(url, params, "application/json, application/geo+json").decode("utf-8", "replace"))


def _text(url: str, params: dict[str, Any]) -> str:
    return _urlopen(url, params, "text/plain").decode("utf-8", "replace")


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


def _radius_degrees(radius_km: float) -> float:
    return min(180.0, max(0.01, float(radius_km) / 111.195))


def _parse_station_text(text: str) -> list[dict[str, Any]]:
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        try:
            network, station = parts[0].strip(), parts[1].strip()
            lat, lon, elev = float(parts[2]), float(parts[3]), float(parts[4])
        except Exception:
            continue
        rows.append({"network": network, "station": station, "latitude": lat, "longitude": lon,
                     "elevation_m": elev, "site_name": parts[5].strip() if len(parts) > 5 else None,
                     "start_time": parts[6].strip() if len(parts) > 6 else None,
                     "end_time": parts[7].strip() if len(parts) > 7 else None})
    return rows


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
                "earthscope_station_discovery": True,
                "seismicity_fusion": True,
                "waveform_surface_registered_not_auto_downloaded": True,
                "deformation_gas_thermal_webcam_surfaces_registered": True,
                "sparse_monitoring_reported_explicitly": True,
            },
        }

    def seismic_stations_near(self, lat: float, lon: float, radius_km: float = 100.0, limit: int = 250) -> list[dict[str, Any]]:
        lat, lon = _validate(lat, lon)
        radius_km = max(1.0, min(float(radius_km), 2000.0))
        text = _text(SOURCES["earthscope_fdsn_station"]["endpoint"], {
            "format": "text", "level": "station", "latitude": lat, "longitude": lon,
            "maxradius": _radius_degrees(radius_km), "nodata": 404,
        })
        out = []
        for s in _parse_station_text(text)[:max(1, min(int(limit), MAX_ITEMS))]:
            slat, slon = s["latitude"], s["longitude"]
            out.append({
                "schema": SCHEMA, "sensor_type": "seismic_station",
                "sensor_id": f"{s['network']}.{s['station']}", "network": s["network"], "station": s["station"],
                "latitude": slat, "longitude": slon, "elevation_m": s["elevation_m"], "site_name": s.get("site_name"),
                "distance_km": round(_haversine_km(lat, lon, slat, slon), 3),
                "source": "earthscope_fdsn_station", "source_is_not_fact": True,
            })
        out.sort(key=lambda x: x["distance_km"])
        return out

    def earthquakes_near(self, lat: float, lon: float, radius_km: float = 100.0, min_magnitude: float = 0.0, limit: int = 250) -> list[dict[str, Any]]:
        lat, lon = _validate(lat, lon)
        data = _json(SOURCES["usgs_fdsn_event"]["endpoint"], {
            "format": "geojson", "latitude": lat, "longitude": lon,
            "maxradiuskm": max(1.0, min(float(radius_km), 2000.0)), "minmagnitude": float(min_magnitude),
            "limit": max(1, min(int(limit), MAX_ITEMS)), "orderby": "time",
        })
        out = []
        for f in data.get("features") or []:
            g = f.get("geometry") or {}; c = g.get("coordinates") or []; p = f.get("properties") or {}
            if len(c) < 2: continue
            out.append({
                "schema": SCHEMA, "hazard": "volcanic_seismicity_candidate", "source_event_id": f.get("id"),
                "latitude": c[1], "longitude": c[0], "depth_km_below_surface": c[2] if len(c) > 2 else None,
                "magnitude": p.get("mag"), "place": p.get("place"),
                "observed_unix": (float(p.get("time")) / 1000.0) if p.get("time") is not None else None,
                "retrieved_unix": time.time(), "distance_km": round(_haversine_km(lat, lon, float(c[1]), float(c[0])), 3),
                "source": "usgs_fdsn_event", "source_is_not_fact": True,
            })
        return out

    def volcano_picture(self, name: str, lat: float, lon: float, radius_km: float = 100.0) -> dict[str, Any]:
        lat, lon = _validate(lat, lon); failures: dict[str, str] = {}
        try: stations = self.seismic_stations_near(lat, lon, radius_km)
        except Exception as e: stations = []; failures["stations"] = f"{type(e).__name__}:{e}"[:500]
        try: quakes = self.earthquakes_near(lat, lon, radius_km)
        except Exception as e: quakes = []; failures["earthquakes"] = f"{type(e).__name__}:{e}"[:500]
        coverage = "dense" if len(stations) >= 8 else "moderate" if len(stations) >= 3 else "sparse" if stations else "no_public_station_discovery"
        return {
            "schema": SCHEMA, "volcano": {"name": str(name), "latitude": lat, "longitude": lon}, "radius_km": float(radius_km),
            "seismic_stations": stations, "recent_earthquakes": quakes, "monitoring_coverage": coverage,
            "reference_surfaces": {
                "usgs_vhp": SOURCES["usgs_vhp"], "smithsonian_gvp": SOURCES["smithsonian_gvp"], "earthscope": SOURCES["earthscope"],
                "waveforms": SOURCES["earthscope_fdsn_dataselect"],
                "deformation": "use public GNSS/InSAR when available", "gas": "use public SO2/CO2/MultiGAS/remote-sensing feeds when available",
                "thermal": "use public satellite/thermal-camera products when available", "webcam": "use observatory webcams where public",
            },
            "rules": {"station_proximity_does_not_prove_volcanic_signal": True, "earthquake_proximity_does_not_prove_volcanic_origin": True,
                      "absence_of_public_station_does_not_mean_unmonitored": True, "no_fake_sensor_assignment": True},
            "failures": failures, "retrieved_unix": time.time(), "source_is_not_fact": True,
        }

    def global_volcano_sensor_contract(self) -> dict[str, Any]:
        return {"schema": SCHEMA,
                "goal": "Every known volcano can be queried against nearby public sensors and evidence without inventing instrumentation.",
                "sensor_classes": ["seismic", "gnss_deformation", "insar_deformation", "gas", "thermal", "webcam", "infrasound", "satellite"],
                "coverage_rule": "discover what exists per volcano; explicitly report sparse or unavailable public coverage",
                "source_is_not_fact": True}


def describe() -> dict[str, Any]: return VolcanoSensorFusion().status()
if __name__ == "__main__": print(json.dumps(describe(), indent=2, sort_keys=True))
