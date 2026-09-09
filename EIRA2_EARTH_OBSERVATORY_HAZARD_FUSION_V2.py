from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

SCHEMA = "eira2_earth_observatory_hazard_fusion_v2"
ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
STATE = ROOT / "eira_probe" / "earth_observatory_v2"
SNAPSHOTS = STATE / "snapshots"
EXPORTS = STATE / "exports"
for p in (STATE, SNAPSHOTS, EXPORTS):
    p.mkdir(parents=True, exist_ok=True)

USER_AGENT = "EIRA2-Earth-Observatory/2.0 (public-read-only; geospatial-fusion)"
TIMEOUT = 20
MAX_ITEMS = 250

SOURCES = {
    "usgs_earthquakes": {
        "endpoint": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson",
        "mode": "near_real_time_geojson",
        "location_native": True,
    },
    "nws_alerts": {
        "endpoint": "https://api.weather.gov/alerts/active",
        "mode": "active_geojson_cap",
        "location_native": True,
    },
    "noaa_nwps": {
        "endpoint": "https://api.water.noaa.gov/nwps/v1",
        "mode": "gauge_observed_forecast",
        "location_native": True,
    },
    "nws_points": {
        "endpoint": "https://api.weather.gov/points/{lat},{lon}",
        "mode": "point_weather_mapping",
        "location_native": True,
    },
    "goes": {
        "mode": "satellite_layer_registry",
        "location_native": True,
        "note": "Satellite raster/product integration attaches above this geospatial spine while preserving source footprints and timestamps.",
    },
    "nexrad_mrms": {
        "mode": "radar_layer_registry",
        "location_native": True,
        "note": "Radar grids attach as evidence layers without replacing source geometry.",
    },
}


def _json(url: str, params: dict[str, Any] | None = None) -> Any:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _coords_from_geometry(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not isinstance(geometry, dict):
        return None, None
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
        try:
            return float(coords[1]), float(coords[0])
        except Exception:
            return None, None
    return None, None


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def _point_in_ring(lat: float, lon: float, ring: list[Any]) -> bool:
    pts = []
    for p in ring:
        if isinstance(p, list) and len(p) >= 2:
            try:
                pts.append((float(p[1]), float(p[0])))
            except Exception:
                pass
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]
        yj, xj = pts[j]
        if ((yi > lat) != (yj > lat)):
            x_cross = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-300) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _point_in_geometry(lat: float, lon: float, geometry: dict[str, Any] | None) -> bool:
    if not isinstance(geometry, dict):
        return False
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon" and isinstance(coords, list) and coords:
        if not _point_in_ring(lat, lon, coords[0]):
            return False
        return not any(_point_in_ring(lat, lon, hole) for hole in coords[1:] if isinstance(hole, list))
    if gtype == "MultiPolygon" and isinstance(coords, list):
        return any(_point_in_geometry(lat, lon, {"type": "Polygon", "coordinates": poly}) for poly in coords if isinstance(poly, list))
    return False


def _geometry_distance_km(lat: float, lon: float, geometry: dict[str, Any] | None) -> float | None:
    if not isinstance(geometry, dict):
        return None
    if _point_in_geometry(lat, lon, geometry):
        return 0.0
    plat, plon = _coords_from_geometry(geometry)
    if plat is not None and plon is not None:
        return _haversine_km(lat, lon, plat, plon)
    coords = geometry.get("coordinates")
    gtype = geometry.get("type")
    candidates: list[tuple[float, float]] = []
    def collect(x: Any) -> None:
        if isinstance(x, list):
            if len(x) >= 2 and all(isinstance(v, (int, float)) for v in x[:2]):
                candidates.append((float(x[1]), float(x[0])))
            else:
                for y in x:
                    collect(y)
    if gtype in ("Polygon", "MultiPolygon", "LineString", "MultiLineString"):
        collect(coords)
    if not candidates:
        return None
    return min(_haversine_km(lat, lon, a, b) for a, b in candidates)


def _event(*, source: str, event_id: str, hazard: str, title: str,
           geometry: dict[str, Any] | None, observed_unix: float | None,
           properties: dict[str, Any], sensor_id: str | None = None,
           source_url: str | None = None) -> dict[str, Any]:
    lat, lon = _coords_from_geometry(geometry)
    return {
        "schema": SCHEMA,
        "source": source,
        "source_event_id": str(event_id),
        "sensor_id": sensor_id,
        "hazard": hazard,
        "title": title,
        "observed_unix": observed_unix,
        "geometry": geometry,
        "latitude": lat,
        "longitude": lon,
        "coordinate_order": "lat_lon",
        "pinpoint": {
            "has_point_coordinate": lat is not None and lon is not None,
            "source_geometry_preserved": True,
            "supports_polygon_containment": True,
            "do_not_invent_precision": True,
        },
        "properties": properties,
        "source_url": source_url,
        "source_is_not_fact": True,
    }


def _kml_coordinates(seq: list[Any]) -> str:
    out = []
    for p in seq:
        if isinstance(p, list) and len(p) >= 2:
            try:
                alt = float(p[2]) if len(p) > 2 and p[2] is not None else 0.0
                out.append(f"{float(p[0]):.8f},{float(p[1]):.8f},{alt:.3f}")
            except Exception:
                pass
    return " ".join(out)


def _geometry_to_kml(geometry: dict[str, Any] | None) -> str:
    if not isinstance(geometry, dict):
        return ""
    gtype = geometry.get("type")
    c = geometry.get("coordinates")
    if gtype == "Point" and isinstance(c, list) and len(c) >= 2:
        return f"<Point><coordinates>{float(c[0]):.8f},{float(c[1]):.8f},{float(c[2]) if len(c)>2 and c[2] is not None else 0.0:.3f}</coordinates></Point>"
    if gtype == "LineString" and isinstance(c, list):
        return f"<LineString><coordinates>{_kml_coordinates(c)}</coordinates></LineString>"
    if gtype == "Polygon" and isinstance(c, list) and c:
        outer = _kml_coordinates(c[0])
        holes = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{_kml_coordinates(r)}</coordinates></LinearRing></innerBoundaryIs>" for r in c[1:] if isinstance(r, list))
        return f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>{holes}</Polygon>"
    if gtype == "MultiPolygon" and isinstance(c, list):
        parts = "".join(_geometry_to_kml({"type": "Polygon", "coordinates": poly}) for poly in c if isinstance(poly, list))
        return f"<MultiGeometry>{parts}</MultiGeometry>"
    if gtype == "MultiLineString" and isinstance(c, list):
        parts = "".join(_geometry_to_kml({"type": "LineString", "coordinates": line}) for line in c if isinstance(line, list))
        return f"<MultiGeometry>{parts}</MultiGeometry>"
    return ""


class EarthObservatory:
    def status(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "root": str(STATE),
            "sources": SOURCES,
            "policy": {
                "public_read_only": True,
                "near_real_time_when_source_supports_it": True,
                "preserve_native_geometry": True,
                "attach_sensor_coordinates": True,
                "google_earth_kml_export": True,
                "google_earth_polygon_export": True,
                "geojson_export": True,
                "polygon_aware_local_fusion": True,
                "no_fake_precision": True,
                "sensor_fusion_is_evidence_correlation": True,
                "source_is_not_fact": True,
            },
        }

    def earthquakes(self, limit: int = 100) -> list[dict[str, Any]]:
        data = _json(SOURCES["usgs_earthquakes"]["endpoint"])
        out = []
        for f in (data.get("features") or [])[: max(1, min(int(limit), MAX_ITEMS))]:
            p = f.get("properties") or {}
            geom = f.get("geometry")
            out.append(_event(
                source="usgs_earthquakes",
                event_id=f.get("id") or p.get("code") or "unknown",
                hazard="earthquake",
                title=p.get("title") or p.get("place") or "Earthquake",
                geometry=geom,
                observed_unix=(float(p["time"]) / 1000.0 if p.get("time") is not None else None),
                properties={
                    "magnitude": p.get("mag"), "place": p.get("place"), "alert": p.get("alert"),
                    "status": p.get("status"), "tsunami": p.get("tsunami"), "felt": p.get("felt"),
                    "mmi": p.get("mmi"), "cdi": p.get("cdi"), "depth_km": ((geom or {}).get("coordinates") or [None, None, None])[2]
                    if isinstance((geom or {}).get("coordinates"), list) and len((geom or {}).get("coordinates")) > 2 else None,
                },
                source_url=p.get("url"),
            ))
        return out

    def active_weather_alerts(self, limit: int = 150) -> list[dict[str, Any]]:
        data = _json(SOURCES["nws_alerts"]["endpoint"])
        out = []
        for f in (data.get("features") or [])[: max(1, min(int(limit), MAX_ITEMS))]:
            p = f.get("properties") or {}
            hazard = str(p.get("event") or "weather_alert").lower().replace(" ", "_")
            out.append(_event(
                source="nws_alerts",
                event_id=p.get("id") or f.get("id") or "unknown",
                hazard=hazard,
                title=p.get("headline") or p.get("event") or "NWS Alert",
                geometry=f.get("geometry"),
                observed_unix=None,
                properties={
                    "event": p.get("event"), "severity": p.get("severity"), "certainty": p.get("certainty"),
                    "urgency": p.get("urgency"), "areaDesc": p.get("areaDesc"), "effective": p.get("effective"),
                    "expires": p.get("expires"), "senderName": p.get("senderName"), "description": p.get("description"),
                    "instruction": p.get("instruction"),
                },
                source_url=p.get("@id") or p.get("id"),
            ))
        return out

    def water_gauge(self, gauge_id: str) -> dict[str, Any]:
        gid = urllib.parse.quote(str(gauge_id).strip(), safe="")
        meta = _json(f"https://api.water.noaa.gov/nwps/v1/gauges/{gid}")
        stageflow = _json(f"https://api.water.noaa.gov/nwps/v1/gauges/{gid}/stageflow")
        lat = meta.get("latitude") or (meta.get("location") or {}).get("latitude")
        lon = meta.get("longitude") or (meta.get("location") or {}).get("longitude")
        geometry = None
        try:
            geometry = {"type": "Point", "coordinates": [float(lon), float(lat)]}
        except Exception:
            pass
        return _event(
            source="noaa_nwps",
            event_id=gauge_id,
            sensor_id=gauge_id,
            hazard="river_flood_hydrology",
            title=meta.get("name") or meta.get("lid") or gauge_id,
            geometry=geometry,
            observed_unix=time.time(),
            properties={"gauge": meta, "stageflow": stageflow},
            source_url=f"https://water.noaa.gov/gauges/{urllib.parse.quote(str(gauge_id))}",
        )

    def point_context(self, lat: float, lon: float) -> dict[str, Any]:
        lat, lon = float(lat), float(lon)
        nws = _json(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
        alerts = _json("https://api.weather.gov/alerts/active", {"point": f"{lat:.4f},{lon:.4f}"})
        return {
            "schema": SCHEMA,
            "point": {"latitude": lat, "longitude": lon},
            "nws_point": nws,
            "active_alerts": alerts,
            "source_is_not_fact": True,
        }

    def fuse_near_point(self, lat: float, lon: float, radius_km: float = 100.0) -> dict[str, Any]:
        lat, lon, radius_km = float(lat), float(lon), max(1.0, float(radius_km))
        events, failures = [], {}
        for name, fn in (("earthquakes", self.earthquakes), ("weather_alerts", self.active_weather_alerts)):
            try:
                for e in fn():
                    d = _geometry_distance_km(lat, lon, e.get("geometry"))
                    if d is None:
                        continue
                    if d <= radius_km:
                        x = dict(e)
                        x["distance_km"] = round(d, 3)
                        x["contains_fusion_point"] = bool(d == 0.0 and _point_in_geometry(lat, lon, e.get("geometry")))
                        events.append(x)
            except Exception as exc:
                failures[name] = f"{type(exc).__name__}:{exc}"[:500]
        events.sort(key=lambda x: x.get("distance_km", 1e99))
        return {
            "schema": SCHEMA,
            "fusion_center": {"latitude": lat, "longitude": lon, "radius_km": radius_km},
            "event_count": len(events),
            "events": events,
            "failures": failures,
            "interpretation": "Geometry-aware evidence correlation only; source products retain their own authority, uncertainty, and native geometry.",
        }

    def global_snapshot(self) -> dict[str, Any]:
        failures = {}
        try:
            quakes = self.earthquakes()
        except Exception as exc:
            quakes, failures["earthquakes"] = [], f"{type(exc).__name__}:{exc}"[:500]
        try:
            alerts = self.active_weather_alerts()
        except Exception as exc:
            alerts, failures["weather_alerts"] = [], f"{type(exc).__name__}:{exc}"[:500]
        snap = {
            "schema": SCHEMA,
            "snapshot_unix": time.time(),
            "earthquakes": quakes,
            "weather_alerts": alerts,
            "failures": failures,
            "source_is_not_fact": True,
        }
        path = SNAPSHOTS / f"earth_{int(snap['snapshot_unix'])}.json"
        path.write_text(json.dumps(snap, indent=2, sort_keys=True))
        return snap

    def export_geojson(self, events: list[dict[str, Any]], filename: str = "eira_earth_events.geojson") -> str:
        features = []
        for e in events:
            geom = e.get("geometry")
            if not isinstance(geom, dict):
                continue
            props = {k: v for k, v in e.items() if k != "geometry"}
            features.append({"type": "Feature", "geometry": geom, "properties": props})
        path = EXPORTS / Path(filename).name
        path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))
        return str(path.relative_to(ROOT))

    def export_kml(self, events: list[dict[str, Any]], filename: str = "eira_earth_events.kml") -> str:
        placemarks = []
        for e in events:
            geom_xml = _geometry_to_kml(e.get("geometry"))
            if not geom_xml:
                continue
            name = escape(str(e.get("title") or e.get("hazard") or "EIRA Earth event"))
            desc = escape(json.dumps({
                "source": e.get("source"), "hazard": e.get("hazard"), "sensor_id": e.get("sensor_id"),
                "source_event_id": e.get("source_event_id"), "properties": e.get("properties"),
            }, ensure_ascii=False)[:12000])
            placemarks.append(f"<Placemark><name>{name}</name><description>{desc}</description>{geom_xml}</Placemark>")
        body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>" \
               "<kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>" + "".join(placemarks) + "</Document></kml>"
        path = EXPORTS / Path(filename).name
        path.write_text(body)
        return str(path.relative_to(ROOT))


def describe() -> dict[str, Any]:
    return EarthObservatory().status()


if __name__ == "__main__":
    print(json.dumps(EarthObservatory().status(), indent=2, sort_keys=True))
