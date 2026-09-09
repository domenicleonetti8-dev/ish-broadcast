from __future__ import annotations
import json, time
from typing import Any

SCHEMA="eira2_planetary_awareness_v1"

class PlanetaryAwareness:
    def __init__(self):
        from eira2.evidence.earth_observatory_hazard_fusion import EarthObservatory
        from eira2.evidence.air_space_watch import AirSpaceWatch
        self.earth=EarthObservatory()
        self.airspace=AirSpaceWatch()

    def status(self)->dict[str,Any]:
        return {
            "schema":SCHEMA,
            "earth_observatory":self.earth.status(),
            "air_space_watch":self.airspace.status(),
            "contract":{
                "one_geospatial_spine":True,
                "geojson_coordinate_order":"longitude_latitude",
                "explicit_lat_lon_fields":True,
                "google_earth_outputs":True,
                "source_provenance_preserved":True,
                "uncertainty_preserved":True,
                "source_is_not_fact":True,
                "unresolved_is_not_exotic":True,
                "public_read_only":True,
            },
        }

    def point_picture(self,lat:float,lon:float,radius_km:float=100.0,aircraft_limit:int=200)->dict[str,Any]:
        lat=float(lat);lon=float(lon);radius_km=max(1.0,float(radius_km))
        earth_fail=None;air_fail=None
        try: earth=self.earth.fuse_near_point(lat,lon,radius_km)
        except Exception as e:
            earth={"events":[]};earth_fail=f"{type(e).__name__}:{e}"[:500]
        deg=max(radius_km/111.0,0.1)
        bbox=(max(-90,lat-deg),max(-180,lon-deg),min(90,lat+deg),min(180,lon+deg))
        try:
            planes=self.airspace.aircraft(bbox=bbox,limit=aircraft_limit,record=False)
            nearby=[]
            center={"latitude":lat,"longitude":lon}
            for p in planes:
                d=self.airspace_distance(center,p)
                if d is not None and d<=radius_km:
                    q=dict(p);q["distance_km"]=round(d,3);nearby.append(q)
            nearby.sort(key=lambda x:x["distance_km"])
        except Exception as e:
            nearby=[];air_fail=f"{type(e).__name__}:{e}"[:500]
        return {
            "schema":SCHEMA,
            "center":{"latitude":lat,"longitude":lon,"radius_km":radius_km},
            "earth_events":earth.get("events",[]),
            "aircraft":nearby,
            "failures":{"earth":earth_fail,"aircraft":air_fail},
            "retrieved_unix":time.time(),
            "source_is_not_fact":True,
        }

    def airspace_distance(self,a:dict[str,Any],b:dict[str,Any])->float|None:
        import math
        vals=(a.get("latitude"),a.get("longitude"),b.get("latitude"),b.get("longitude"))
        if any(v is None for v in vals): return None
        r=6371.0088
        p1=math.radians(float(vals[0]));p2=math.radians(float(vals[2]))
        dp=p2-p1;dl=math.radians(((float(vals[3])-float(vals[1])+180)%360)-180)
        q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*r*math.asin(min(1.0,math.sqrt(q)))

    def object_context(self,observation:dict[str,Any],radius_km:float=25.0)->dict[str,Any]:
        lat=observation.get("latitude");lon=observation.get("longitude")
        context=None
        if lat is not None and lon is not None:
            context=self.point_picture(float(lat),float(lon),radius_km)
        planes=(context or {}).get("aircraft",[])
        correlation=self.airspace.correlate(observation,{"aircraft":planes},spatial_km=radius_km,time_seconds=180)
        return {
            "schema":SCHEMA,
            "observation":observation,
            "airspace_correlation":correlation,
            "earth_context":context,
            "decision_rule":"Known explanations are tested first. Unresolved means unresolved, not exotic.",
            "source_is_not_fact":True,
        }

    def global_watch_summary(self)->dict[str,Any]:
        out={"schema":SCHEMA,"retrieved_unix":time.time(),"failures":{},"source_is_not_fact":True}
        for name,fn in (
            ("earth",self.earth.global_snapshot),
            ("fireballs",lambda:self.airspace.fireballs(100)),
            ("sentry",lambda:self.airspace.sentry(100)),
            ("reentry_candidates",lambda:self.airspace.reentry_candidates(100)),
        ):
            try: out[name]=fn()
            except Exception as e:
                out[name]=[] if name!="earth" else {}
                out["failures"][name]=f"{type(e).__name__}:{e}"[:500]
        return out

def describe()->dict[str,Any]:
    return PlanetaryAwareness().status()

if __name__=="__main__":
    print(json.dumps(describe(),indent=2,sort_keys=True))
