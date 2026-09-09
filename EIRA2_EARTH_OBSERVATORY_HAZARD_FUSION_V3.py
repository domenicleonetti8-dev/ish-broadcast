from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

SCHEMA = "eira2_earth_observatory_hazard_fusion_v3"
ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
STATE = ROOT / "eira_probe" / "earth_observatory_v3"
SNAPSHOTS = STATE / "snapshots"
EXPORTS = STATE / "exports"
for p in (STATE, SNAPSHOTS, EXPORTS):
    p.mkdir(parents=True, exist_ok=True)

USER_AGENT = "EIRA2-Earth-Observatory/3.0 (public-read-only; geospatial-fusion)"
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
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _validate_latlon(lat: float, lon: float) -> tuple[float, float]:
    lat, lon = float(lat), float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("coordinates_must_be_finite")
    if not -90.0 <= lat <= 90.0:
        raise ValueError("latitude_out_of_range")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("longitude_out_of_range")
    return lat, lon


def _parse_iso_unix(value: Any) -> float | None:
    if not value:
        return None
    try:
        s = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def _coords_from_geometry(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not isinstance(geometry, dict):
        return None, None
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
        try:
            lat, lon = _validate_latlon(float(coords[1]), float(coords[0]))
            return lat, lon
        except Exception:
            return None, None
    return None, None


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    a_lat, a_lon = _validate_latlon(a_lat, a_lon)
    b_lat, b_lon = _validate_latlon(b_lat, b_lon)
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(((b_lon - a_lon + 180.0) % 360.0) - 180.0)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(x)))


def _unwrap_lon(lon: float, reference_lon: float) -> float:
    return reference_lon + ((float(lon) - reference_lon + 180.0) % 360.0) - 180.0


def _point_in_ring(lat: float, lon: float, ring: list[Any]) -> bool:
    lat, lon = _validate_latlon(lat, lon)
    pts: list[tuple[float, float]] = []
    for p in ring:
        if isinstance(p, list) and len(p) >= 2:
            try:
                py = float(p[1])
                px = _unwrap_lon(float(p[0]), lon)
                if -90.0 <= py <= 90.0:
                    pts.append((py, px))
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
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
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
        return any(
            _point_in_geometry(lat, lon, {"type": "Polygon", "coordinates": poly})
            for poly in coords if isinstance(poly, list)
        )
    if gtype == "GeometryCollection":
        return any(_point_in_geometry(lat, lon, g) for g in (geometry.get("geometries") or []) if isinstance(g, dict))
    return False


def _segment_distance_km(lat: float, lon: float, a: list[Any], b: list[Any]) -> float | None:
    try:
        lat, lon = _validate_latlon(lat, lon)
        alat, alon = float(a[1]), _unwrap_lon(float(a[0]), lon)
        blat, blon = float(b[1]), _unwrap_lon(float(b[0]), lon)
        if not (-90 <= alat <= 90 and -90 <= blat <= 90):
            return None
        r = 6371.0088
        lat0 = math.radians(lat)
        ax = math.radians(alon - lon) * math.cos(lat0) * r
        ay = math.radians(alat - lat) * r
        bx = math.radians(blon - lon) * math.cos(lat0) * r
        by = math.radians(blat - lat) * r
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        t = 0.0 if den == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / den))
        return math.hypot(ax + t * dx, ay + t * dy)
    except Exception:
        return None


def _line_distance_km(lat: float, lon: float, line: Any, closed: bool = False) -> float | None:
    if not isinstance(line, list) or len(line) < 2:
        return None
    vals = [d for i in range(len(line) - 1) if (d := _segment_distance_km(lat, lon, line[i], line[i + 1])) is not None]
    if closed and line and line[0] != line[-1]:
        d = _segment_distance_km(lat, lon, line[-1], line[0])
        if d is not None:
            vals.append(d)
    return min(vals) if vals else None


def _geometry_distance_km(lat: float, lon: float, geometry: dict[str, Any] | None) -> float | None:
    lat, lon = _validate_latlon(lat, lon)
    if not isinstance(geometry, dict):
        return None
    if _point_in_geometry(lat, lon, geometry):
        return 0.0
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Point":
        plat, plon = _coords_from_geometry(geometry)
        return _haversine_km(lat, lon, plat, plon) if plat is not None and plon is not None else None
    if gtype == "LineString":
        return _line_distance_km(lat, lon, coords)
    if gtype == "MultiLineString" and isinstance(coords, list):
        vals = [v for line in coords if (v := _line_distance_km(lat, lon, line)) is not None]
        return min(vals) if vals else None
    if gtype == "Polygon" and isinstance(coords, list):
        vals = [v for ring in coords if (v := _line_distance_km(lat, lon, ring, closed=True)) is not None]
        return min(vals) if vals else None
    if gtype == "MultiPolygon" and isinstance(coords, list):
        vals = [
            v for poly in coords
            if (v := _geometry_distance_km(lat, lon, {"type": "Polygon", "coordinates": poly})) is not None
        ]
        return min(vals) if vals else None
    if gtype == "MultiPoint" and isinstance(coords, list):
        vals = []
        for p in coords:
            try:
                vals.append(_haversine_km(lat, lon, float(p[1]), float(p[0])))
            except Exception:
                pass
        return min(vals) if vals else None
    if gtype == "GeometryCollection":
        vals = [
            v for g in (geometry.get("geometries") or []) if isinstance(g, dict)
            if (v := _geometry_distance_km(lat, lon, g)) is not None
        ]
        return min(vals) if vals else None
    return None


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
        "retrieved_unix": time.time(),
        "geometry": geometry,
        "latitude": lat,
        "longitude": lon,
        "coordinate_order": "lat_lon",
        "pinpoint": {
            "has_point_coordinate": lat is not None and lon is not None,
            "source_geometry_preserved": True,
            "supports_polygon_containment": True,
            "supports_boundary_segment_distance": True,
            "do_not_invent_precision": True,
        },
        "properties": properties,
        "source_url": source_url,
        "source_is_not_fact": True,
    }


def _alert_event(feature: dict[str, Any]) -> dict[str, Any]:
    p = feature.get("properties") or {}
    hazard = str(p.get("event") or "weather_alert").lower().replace(" ", "_")
    return _event(
        source="nws_alerts",
        event_id=p.get("id") or feature.get("id") or "unknown",
        hazard=hazard,
        title=p.get("headline") or p.get("event") or "NWS Alert",
        geometry=feature.get("geometry"),
        observed_unix=_parse_iso_unix(p.get("effective") or p.get("sent") or p.get("onset")),
        properties={
            "event": p.get("event"), "severity": p.get("severity"), "certainty": p.get("certainty"),
            "urgency": p.get("urgency"), "areaDesc": p.get("areaDesc"), "effective": p.get("effective"),
            "onset": p.get("onset"), "expires": p.get("expires"), "ends": p.get("ends"),
            "senderName": p.get("senderName"), "description": p.get("description"),
            "instruction": p.get("instruction"), "geocode": p.get("geocode"), "affectedZones": p.get("affectedZones"),
        },
        source_url=feature.get("id") or p.get("id"),
    )


def _kml_coordinates(seq: list[Any]) -> str:
    out = []
    for p in seq:
        if isinstance(p, list) and len(p) >= 2:
            try:
                lon, lat = float(p[0]), float(p[1])
                _validate_latlon(lat, lon)
                out.append(f"{lon:.8f},{lat:.8f},0")
            except Exception:
                pass
    return " ".join(out)


def _geometry_to_kml(geometry: dict[str, Any] | None) -> str:
    if not isinstance(geometry, dict):
        return ""
    gtype = geometry.get("type")
    c = geometry.get("coordinates")
    if gtype == "Point" and isinstance(c, list) and len(c) >= 2:
        try:
            lat, lon = _validate_latlon(float(c[1]), float(c[0]))
            return f"<Point><altitudeMode>clampToGround</altitudeMode><coordinates>{lon:.8f},{lat:.8f},0</coordinates></Point>"
        except Exception:
            return ""
    if gtype == "LineString" and isinstance(c, list):
        return f"<LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode><coordinates>{_kml_coordinates(c)}</coordinates></LineString>"
    if gtype == "Polygon" and isinstance(c, list) and c:
        outer = _kml_coordinates(c[0])
        holes = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{_kml_coordinates(r)}</coordinates></LinearRing></innerBoundaryIs>"
            for r in c[1:] if isinstance(r, list)
        )
        return f"<Polygon><altitudeMode>clampToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>{holes}</Polygon>"
    if gtype == "MultiPolygon" and isinstance(c, list):
        parts = "".join(_geometry_to_kml({"type": "Polygon", "coordinates": poly}) for poly in c if isinstance(poly, list))
        return f"<MultiGeometry>{parts}</MultiGeometry>"
    if gtype == "MultiLineString" and isinstance(c, list):
        parts = "".join(_geometry_to_kml({"type": "LineString", "coordinates": line}) for line in c if isinstance(line, list))
        return f"<MultiGeometry>{parts}</MultiGeometry>"
    if gtype == "MultiPoint" and isinstance(c, list):
        parts = "".join(_geometry_to_kml({"type": "Point", "coordinates": p}) for p in c if isinstance(p, list))
        return f"<MultiGeometry>{parts}</MultiGeometry>"
    if gtype == "GeometryCollection":
        parts = "".join(_geometry_to_kml(g) for g in (geometry.get("geometries") or []) if isinstance(g, dict))
        return f"<MultiGeometry>{parts}</MultiGeometry>" if parts else ""
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
                "google_earth_surface_geometry_only": True,
                "earthquake_depth_kept_as_metadata_not_kml_altitude": True,
                "geojson_export": True,
                "polygon_aware_local_fusion": True,
                "segment_aware_boundary_distance": True,
                "nws_point_geolocation_fallback": True,
                "separate_observed_and_retrieved_times": True,
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
                    "mmi": p.get("mmi"), "cdi": p.get("cdi"), "updated": p.get("updated"),
                    "depth_km_below_surface": ((geom or {}).get("coordinates") or [None, None, None])[2]
                    if isinstance((geom or {}).get("coordinates"), list) and len((geom or {}).get("coordinates")) > 2 else None,
                },
                source_url=p.get("url"),
            ))
        return out

    def active_weather_alerts(self, limit: int = 150) -> list[dict[str, Any]]:
        data = _json(SOURCES["nws_alerts"]["endpoint"])
        return [_alert_event(f) for f in (data.get("features") or [])[: max(1, min(int(limit), MAX_ITEMS))] if isinstance(f, dict)]

    def water_gauge(self, gauge_id: str) -> dict[str, Any]:
        gid = urllib.parse.quote(str(gauge_id).strip(), safe="")
        if not gid:
            raise ValueError("gauge_id_required")
        meta = _json(f"https://api.water.noaa.gov/nwps/v1/gauges/{gid}")
        stageflow = _json(f"https://api.water.noaa.gov/nwps/v1/gauges/{gid}/stageflow")
        lat = meta.get("latitude") or (meta.get("location") or {}).get("latitude")
        lon = meta.get("longitude") or (meta.get("location") or {}).get("longitude")
        geometry = None
        try:
            plat, plon = _validate_latlon(float(lat), float(lon))
            geometry = {"type": "Point", "coordinates": [plon, plat]}
        except Exception:
            pass
        return _event(
            source="noaa_nwps",
            event_id=gauge_id,
            sensor_id=gauge_id,
            hazard="river_flood_hydrology",
            title=meta.get("name") or meta.get("lid") or gauge_id,
            geometry=geometry,
            observed_unix=None,
            properties={"gauge": meta, "stageflow": stageflow, "time_note": "Source stage/flow timestamps remain authoritative; retrieval time is separate."},
            source_url=f"https://water.noaa.gov/gauges/{urllib.parse.quote(str(gauge_id))}",
        )

    def point_context(self, lat: float, lon: float) -> dict[str, Any]:
        lat, lon = _validate_latlon(lat, lon)
        nws = _json(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
        alerts = _json("https://api.weather.gov/alerts/active", {"point": f"{lat:.4f},{lon:.4f}"})
        return {
            "schema": SCHEMA,
            "point": {"latitude": lat, "longitude": lon},
            "nws_point": nws,
            "active_alerts": alerts,
            "retrieved_unix": time.time(),
            "source_is_not_fact": True,
        }

    def fuse_near_point(self, lat: float, lon: float, radius_km: float = 100.0) -> dict[str, Any]:
        lat, lon = _validate_latlon(lat, lon)
        radius_km = max(1.0, float(radius_km))
        events: list[dict[str, Any]] = []
        failures: dict[str, str] = {}
        seen: set[str] = set()

        try:
            for e in self.earthquakes():
                d = _geometry_distance_km(lat, lon, e.get("geometry"))
                if d is not None and d <= radius_km:
                    x = dict(e)
                    x["distance_km"] = round(d, 3)
                    x["contains_fusion_point"] = False
                    events.append(x)
                    seen.add(f"{e.get('source')}:{e.get('source_event_id')}")
        except Exception as exc:
            failures["earthquakes"] = f"{type(exc).__name__}:{exc}"[:500]

        try:
            for e in self.active_weather_alerts():
                d = _geometry_distance_km(lat, lon, e.get("geometry"))
                if d is None or d > radius_km:
                    continue
                x = dict(e)
                x["distance_km"] = round(d, 3)
                x["contains_fusion_point"] = bool(_point_in_geometry(lat, lon, e.get("geometry")))
                events.append(x)
                seen.add(f"{e.get('source')}:{e.get('source_event_id')}")
        except Exception as exc:
            failures["weather_alert_geometry"] = f"{type(exc).__name__}:{exc}"[:500]

        try:
            point_alerts = _json("https://api.weather.gov/alerts/active", {"point": f"{lat:.4f},{lon:.4f}"})
            for f in point_alerts.get("features") or []:
                if not isinstance(f, dict):
                    continue
                e = _alert_event(f)
                key = f"{e.get('source')}:{e.get('source_event_id')}"
                if key in seen:
                    continue
                x = dict(e)
                x["distance_km"] = 0.0
                x["contains_fusion_point"] = True
                x["point_geolocation_match"] = True
                events.append(x)
                seen.add(key)
        except Exception as exc:
            failures["weather_alert_point_geolocation"] = f"{type(exc).__name__}:{exc}"[:500]

        events.sort(key=lambda x: (x.get("distance_km", 1e99), -(x.get("observed_unix") or 0.0)))
        return {
            "schema": SCHEMA,
            "fusion_center": {"latitude": lat, "longitude": lon, "radius_km": radius_km},
            "event_count": len(events),
            "events": events,
            "failures": failures,
            "interpretation": "Geometry-aware evidence correlation only; source products retain authority, uncertainty, timestamps, and native geometry.",
        }

    def global_snapshot(self) -> dict[str, Any]:
        failures: dict[str, str] = {}
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
                "source_event_id": e.get("source_event_id"), "observed_unix": e.get("observed_unix"),
                "retrieved_unix": e.get("retrieved_unix"), "properties": e.get("properties"),
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
