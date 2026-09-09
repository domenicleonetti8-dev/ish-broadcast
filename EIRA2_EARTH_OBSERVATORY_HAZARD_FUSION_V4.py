from __future__ import annotations

import json
from typing import Any

from eira2.evidence.earth_observatory_hazard_fusion_v3_base import EarthObservatory as EarthObservatoryV3
from eira2.evidence.earth_observatory_volcano_monitoring import VolcanoSensorFusion

SCHEMA = "eira2_earth_observatory_hazard_fusion_v4"


class EarthObservatory(EarthObservatoryV3):
    def __init__(self):
        super().__init__()
        self.volcanoes = VolcanoSensorFusion()

    def status(self) -> dict[str, Any]:
        base = super().status()
        return {
            "schema": SCHEMA,
            "v3_geospatial_core": base,
            "volcano_sensor_fusion": self.volcanoes.status(),
            "contract": {
                "segment_aware_boundary_distance": True,
                "polygon_holes_and_multipolygons": True,
                "antimeridian_aware": True,
                "nws_point_geolocation_fallback": True,
                "earthquake_depth_is_metadata_not_kml_altitude": True,
                "separate_observed_and_retrieved_times": True,
                "global_volcano_sensor_discovery": True,
                "no_fake_volcano_sensor_coverage": True,
                "source_is_not_fact": True,
            },
        }

    def volcano_picture(self, name: str, lat: float, lon: float, radius_km: float = 100.0) -> dict[str, Any]:
        return self.volcanoes.volcano_picture(name, lat, lon, radius_km)

    def volcano_sensor_contract(self) -> dict[str, Any]:
        return self.volcanoes.global_volcano_sensor_contract()

    def fuse_volcano_near_point(self, name: str, lat: float, lon: float, radius_km: float = 100.0) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "earth_context": super().fuse_near_point(lat, lon, radius_km),
            "volcano_context": self.volcanoes.volcano_picture(name, lat, lon, radius_km),
            "source_is_not_fact": True,
        }


def describe() -> dict[str, Any]:
    return EarthObservatory().status()


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2, sort_keys=True))
