from __future__ import annotations
import json, math, time
from typing import Any

SCHEMA="eira2_planetary_awareness_v2"

class PlanetaryAwareness:
    def __init__(self):
        from eira2.evidence.earth_observatory_hazard_fusion import EarthObservatory
        from eira2.evidence.air_space_watch import AirSpaceWatch
        self.earth=EarthObservatory()
        self.airspace=AirSpaceWatch()

    def status(self)->dict[str,Any]:
        return {"schema":SCHEMA,"earth_observatory":self.earth.status(),"air_space_watch":self.airspace.status(),
          "contract":{"one_geospatial_spine":True,"geojson_coordinate_order":"longitude_latitude",
          "explicit_lat_lon_fields":True,"google_earth_outputs":True,"source_provenance_preserved":True,
          "uncertainty_preserved":True,"source_is_not_fact":True,"unresolved_is_not_exotic":True,
          "public_read_only":True,"known_explanations_first":True,"multi_domain_resolution":True}}

    def _distance(self,a:dict[str,Any],b:dict[str,Any])->float|None:
        vals=(a.get("latitude"),a.get("longitude"),b.get("latitude"),b.get("longitude"))
        if any(v is None for v in vals):return None
        r=6371.0088;p1=math.radians(float(vals[0]));p2=math.radians(float(vals[2]))
        dp=p2-p1;dl=math.radians(((float(vals[3])-float(vals[1])+180)%360)-180)
        q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*r*math.asin(min(1.0,math.sqrt(q)))

    def point_picture(self,lat:float,lon:float,radius_km:float=100.0,aircraft_limit:int=250)->dict[str,Any]:
        lat=float(lat);lon=float(lon);radius_km=max(1.0,float(radius_km));fail={}
        try:earth=self.earth.fuse_near_point(lat,lon,radius_km)
        except Exception as e:earth={"events":[]};fail["earth"]=f"{type(e).__name__}:{e}"[:500]
        deg=max(radius_km/111.0,0.1)
        bbox=(max(-90,lat-deg),max(-180,lon-deg),min(90,lat+deg),min(180,lon+deg))
        try:
            planes=self.airspace.aircraft(bbox=bbox,limit=aircraft_limit,record=True)
            center={"latitude":lat,"longitude":lon};near=[]
            for p in planes:
                d=self._distance(center,p)
                if d is not None and d<=radius_km:q=dict(p);q["distance_km"]=round(d,3);near.append(q)
            near.sort(key=lambda x:x["distance_km"])
        except Exception as e:near=[];fail["aircraft"]=f"{type(e).__name__}:{e}"[:500]
        return {"schema":SCHEMA,"center":{"latitude":lat,"longitude":lon,"radius_km":radius_km},
          "earth_events":earth.get("events",[]),"aircraft":near,"failures":fail,
          "retrieved_unix":time.time(),"source_is_not_fact":True}

    def _near_fireballs(self,lat:float,lon:float,radius_km:float,time_window_seconds:float=86400.0)->list[dict[str,Any]]:
        out=[];now=time.time();center={"latitude":lat,"longitude":lon}
        try:rows=self.airspace.fireballs(100)
        except Exception:return out
        for x in rows:
            d=self._distance(center,x)
            if d is None or d>radius_km:continue
            t=x.get("observed_unix")
            if t is not None and abs(now-float(t))>time_window_seconds:continue
            q=dict(x);q["distance_km"]=round(d,3);out.append(q)
        return out

    def candidate_sets(self,observation:dict[str,Any],radius_km:float=50.0)->tuple[dict[str,list[dict[str,Any]]],dict[str,Any]]:
        lat=observation.get("latitude");lon=observation.get("longitude");sets={};fail={}
        if lat is not None and lon is not None:
            lat=float(lat);lon=float(lon);deg=max(radius_km/111.0,0.1)
            bbox=(max(-90,lat-deg),max(-180,lon-deg),min(90,lat+deg),min(180,lon+deg))
            try:sets["aircraft"]=self.airspace.aircraft(bbox=bbox,limit=250,record=True)
            except Exception as e:fail["aircraft"]=f"{type(e).__name__}:{e}"[:500]
            try:sets["fireballs"]=self._near_fireballs(lat,lon,max(radius_km,250.0),86400.0)
            except Exception as e:fail["fireballs"]=f"{type(e).__name__}:{e}"[:500]
            try:
                earth=self.earth.fuse_near_point(lat,lon,max(radius_km,25.0))
                events=[]
                for ev in earth.get("events",[]):
                    geom=ev.get("geometry") if isinstance(ev,dict) else None
                    if isinstance(geom,dict) and geom.get("type")=="Point":
                        c=geom.get("coordinates") or []
                        if len(c)>=2:
                            events.append({"schema":SCHEMA,"source":ev.get("source","earth_observatory"),
                              "track_id":ev.get("id") or ev.get("event_id") or "earth_event",
                              "classification":"known_atmospheric_or_sensor_effect",
                              "latitude":c[1],"longitude":c[0],"geometric_altitude_m":None,
                              "velocity_mps":None,"heading_deg":None,"vertical_rate_mps":None,
                              "observed_unix":ev.get("observed_unix"),"properties":ev,"confidence":0.7,
                              "uncertainty":{"earth_context_candidate":True},"source_is_not_fact":True})
                sets["earth_context"]=events
            except Exception as e:fail["earth_context"]=f"{type(e).__name__}:{e}"[:500]
        try:sets["orbital_catalog"]=self.airspace.orbital_objects("active",100)
        except Exception as e:fail["orbital_catalog"]=f"{type(e).__name__}:{e}"[:500]
        try:sets["reentry_catalog"]=self.airspace.reentry_candidates(100)
        except Exception as e:fail["reentry_catalog"]=f"{type(e).__name__}:{e}"[:500]
        return sets,fail

    def resolve_object(self,observation:dict[str,Any],radius_km:float=50.0,time_seconds:float=300.0)->dict[str,Any]:
        sets,fail=self.candidate_sets(observation,radius_km)
        spatial_sets={k:v for k,v in sets.items() if k not in {"orbital_catalog","reentry_catalog"}}
        correlation=self.airspace.correlate(observation,spatial_sets,spatial_km=radius_km,time_seconds=time_seconds)
        cls=correlation.get("classification") or "unresolved_airborne_object"
        best=correlation.get("best_candidate")
        evidence_gaps=[]
        if sets.get("orbital_catalog"):evidence_gaps.append("orbital GP elements present but not current geodetic positions; SGP4 propagation required before spatial identity test")
        if sets.get("reentry_catalog"):evidence_gaps.append("reentry candidates present but no propagated current footprint without SGP4/atmospheric model")
        if not best:evidence_gaps.append("no sufficiently strong spatial-temporal-kinematic candidate")
        return {"schema":SCHEMA,"observation":observation,"classification":cls,
          "correlation":correlation,"candidate_domains":{k:len(v) for k,v in sets.items()},
          "catalog_context":{"orbital":sets.get("orbital_catalog",[])[:20],"reentry":sets.get("reentry_catalog",[])[:20]},
          "failures":fail,"evidence_gaps":evidence_gaps,
          "decision_rule":"Known explanations are tested first. Unresolved means unresolved, not exotic.",
          "source_is_not_fact":True,"retrieved_unix":time.time()}

    def global_watch_summary(self)->dict[str,Any]:
        out={"schema":SCHEMA,"retrieved_unix":time.time(),"failures":{},"source_is_not_fact":True}
        for name,fn in (("earth",self.earth.global_snapshot),("fireballs",lambda:self.airspace.fireballs(100)),
                        ("sentry",lambda:self.airspace.sentry(100)),("reentry_candidates",lambda:self.airspace.reentry_candidates(100))):
            try:out[name]=fn()
            except Exception as e:
                out[name]=[] if name!="earth" else {};out["failures"][name]=f"{type(e).__name__}:{e}"[:500]
        return out

    def export_object_context(self,resolution:dict[str,Any],filename:str="eira_planetary_object_context.geojson")->str:
        tracks=[]
        obs=(resolution.get("correlation") or {}).get("observation")
        if isinstance(obs,dict):tracks.append(obs)
        for m in (resolution.get("correlation") or {}).get("candidates",[])[:20]:
            t=m.get("track")
            if isinstance(t,dict):tracks.append(t)
        return self.airspace.export_geojson(tracks,filename)

def describe()->dict[str,Any]:return PlanetaryAwareness().status()
if __name__=="__main__":print(json.dumps(describe(),indent=2,sort_keys=True))
