from __future__ import annotations
import json, math, time
from typing import Any

SCHEMA="eira2_planetary_awareness_v3"

class PlanetaryAwareness:
    def __init__(self):
        from eira2.evidence.earth_observatory_hazard_fusion import EarthObservatory
        from eira2.evidence.air_space_watch import AirSpaceWatch
        from eira2.evidence.orbital_propagation import OrbitalPropagationEngine
        self.earth=EarthObservatory(); self.airspace=AirSpaceWatch(); self.orbits=OrbitalPropagationEngine()

    def status(self)->dict[str,Any]:
        return {"schema":SCHEMA,"earth_observatory":self.earth.status(),"air_space_watch":self.airspace.status(),"orbital_propagation":self.orbits.status(),
          "contract":{"one_geospatial_spine":True,"known_explanations_first":True,"multi_domain_resolution":True,
          "propagated_orbital_positions":True,"reentry_screening_corridors":True,"uncertainty_preserved":True,
          "source_provenance_preserved":True,"unresolved_is_not_exotic":True,"source_is_not_fact":True}}

    def _distance(self,a:dict[str,Any],b:dict[str,Any])->float|None:
        vals=(a.get("latitude"),a.get("longitude"),b.get("latitude"),b.get("longitude"))
        if any(v is None for v in vals):return None
        r=6371.0088;p1=math.radians(float(vals[0]));p2=math.radians(float(vals[2]))
        dp=p2-p1;dl=math.radians(((float(vals[3])-float(vals[1])+180)%360)-180)
        q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*r*math.asin(min(1.0,math.sqrt(q)))

    def _omm_from_track(self,t:dict[str,Any])->dict[str,Any]:
        p=t.get("properties") or {}
        return {"OBJECT_NAME":p.get("name"),"OBJECT_ID":p.get("object_id"),"NORAD_CAT_ID":p.get("norad_cat_id"),
          "EPOCH":p.get("epoch"),"MEAN_MOTION":p.get("mean_motion"),"ECCENTRICITY":p.get("eccentricity"),
          "INCLINATION":p.get("inclination_deg"),"RA_OF_ASC_NODE":p.get("ra_of_asc_node_deg"),
          "ARG_OF_PERICENTER":p.get("arg_of_pericenter_deg"),"MEAN_ANOMALY":p.get("mean_anomaly_deg"),
          "BSTAR":p.get("bstar"),"MEAN_ELEMENT_THEORY":p.get("mean_element_theory") or "SGP4"}

    def _propagated(self,rows:list[dict[str,Any]],unix:float,classification:str)->list[dict[str,Any]]:
        out=[]
        for t in rows:
            p=self.orbits.propagate_omm(self._omm_from_track(t),unix)
            if not p.get("ok"):continue
            out.append({"schema":SCHEMA,"source":"celestrak+orbital_propagation","track_id":str(t.get("track_id")),
              "classification":classification,"latitude":p.get("latitude"),"longitude":p.get("longitude"),
              "geometric_altitude_m":p.get("geometric_altitude_m"),"barometric_altitude_m":None,
              "velocity_mps":None,"heading_deg":None,"vertical_rate_mps":None,"observed_unix":unix,
              "properties":{"catalog":t.get("properties"),"propagation_model":p.get("model")},
              "confidence":0.92 if p.get("model")=="SGP4" else 0.55,
              "uncertainty":{"radius_km":p.get("uncertainty_radius_km"),"model":p.get("model"),"epoch_age_seconds":p.get("epoch_age_seconds")},
              "source_is_not_fact":True})
        return out

    def point_picture(self,lat:float,lon:float,radius_km:float=100.0)->dict[str,Any]:
        obs={"id":"point_picture","latitude":float(lat),"longitude":float(lon),"observed_unix":time.time(),"sensor_type":"context"}
        sets,fail=self.candidate_sets(obs,radius_km)
        return {"schema":SCHEMA,"center":{"latitude":float(lat),"longitude":float(lon),"radius_km":float(radius_km)},
          "candidate_domains":{k:len(v) for k,v in sets.items()},"candidates":sets,"failures":fail,"source_is_not_fact":True}

    def candidate_sets(self,observation:dict[str,Any],radius_km:float=50.0)->tuple[dict[str,list[dict[str,Any]]],dict[str,Any]]:
        now=float(observation.get("observed_unix") or time.time());lat=observation.get("latitude");lon=observation.get("longitude")
        sets:dict[str,list[dict[str,Any]]]={};fail={}
        if lat is not None and lon is not None:
            lat=float(lat);lon=float(lon);deg=max(float(radius_km)/111.0,0.1);bbox=(max(-90,lat-deg),max(-180,lon-deg),min(90,lat+deg),min(180,lon+deg))
            try:sets["aircraft"]=self.airspace.aircraft(bbox=bbox,limit=250,record=True)
            except Exception as e:fail["aircraft"]=f"{type(e).__name__}:{e}"[:500]
            try:
                earth=self.earth.fuse_near_point(lat,lon,max(float(radius_km),25.0));events=[]
                for ev in earth.get("events",[]):
                    g=ev.get("geometry") if isinstance(ev,dict) else None
                    if isinstance(g,dict) and g.get("type")=="Point":
                        c=g.get("coordinates") or []
                        if len(c)>=2:events.append({"schema":SCHEMA,"source":ev.get("source","earth_observatory"),"track_id":ev.get("id") or ev.get("event_id") or "earth_event",
                          "classification":"known_atmospheric_or_sensor_effect","latitude":c[1],"longitude":c[0],"geometric_altitude_m":None,
                          "velocity_mps":None,"heading_deg":None,"vertical_rate_mps":None,"observed_unix":ev.get("observed_unix"),
                          "properties":ev,"confidence":0.7,"uncertainty":{"earth_context_candidate":True},"source_is_not_fact":True})
                sets["earth_context"]=events
            except Exception as e:fail["earth_context"]=f"{type(e).__name__}:{e}"[:500]
            try:
                fire=[];center={"latitude":lat,"longitude":lon}
                for x in self.airspace.fireballs(100):
                    d=self._distance(center,x)
                    if d is not None and d<=max(float(radius_km),250.0):fire.append(x)
                sets["fireballs"]=fire
            except Exception as e:fail["fireballs"]=f"{type(e).__name__}:{e}"[:500]
        try:
            cat=self.airspace.orbital_objects("active",150);sets["orbital"]=self._propagated(cat,now,"known_orbital_object")
        except Exception as e:fail["orbital"]=f"{type(e).__name__}:{e}"[:500]
        try:
            dec=self.airspace.reentry_candidates(100);sets["reentry"]=self._propagated(dec,now,"reentry_candidate")
        except Exception as e:fail["reentry"]=f"{type(e).__name__}:{e}"[:500]
        return sets,fail

    def resolve_object(self,observation:dict[str,Any],radius_km:float=100.0,time_seconds:float=600.0)->dict[str,Any]:
        sets,fail=self.candidate_sets(observation,radius_km)
        correlation=self.airspace.correlate(observation,sets,spatial_km=float(radius_km),time_seconds=float(time_seconds))
        best=correlation.get("best_candidate");cls=correlation.get("classification") or "unresolved_airborne_object"
        reentry_corridor=None
        if best and best.get("domain")=="reentry":
            tid=str((best.get("track") or {}).get("track_id")); raw=None
            try:
                for t in self.airspace.reentry_candidates(100):
                    if str(t.get("track_id"))==tid:raw=t;break
                if raw:reentry_corridor=self.orbits.reentry_screening_corridor(self._omm_from_track(raw),float(observation.get("observed_unix") or time.time()))
            except Exception as e:fail["reentry_corridor"]=f"{type(e).__name__}:{e}"[:500]
        gaps=[]
        if not self.orbits.status().get("sgp4_available"):gaps.append("true SGP4 library unavailable at runtime; two-body screening fallback in use")
        if cls=="reentry_candidate":gaps.append("reentry corridor is screening-only; atmospheric drag, breakup and ballistic coefficient are not solved")
        if not best:gaps.append("no sufficiently strong multi-domain candidate")
        return {"schema":SCHEMA,"observation":observation,"classification":cls,"correlation":correlation,
          "candidate_domains":{k:len(v) for k,v in sets.items()},"reentry_screening_corridor":reentry_corridor,
          "failures":fail,"evidence_gaps":gaps,"decision_rule":"Known explanations are tested first. Unresolved means unresolved, not exotic.",
          "source_is_not_fact":True,"retrieved_unix":time.time()}

    def global_watch_summary(self)->dict[str,Any]:
        out={"schema":SCHEMA,"retrieved_unix":time.time(),"failures":{},"source_is_not_fact":True}
        for name,fn in (("earth",self.earth.global_snapshot),("fireballs",lambda:self.airspace.fireballs(100)),
                        ("sentry",lambda:self.airspace.sentry(100)),("reentry_candidates",lambda:self.airspace.reentry_candidates(100))):
            try:out[name]=fn()
            except Exception as e:out[name]=[] if name!="earth" else {};out["failures"][name]=f"{type(e).__name__}:{e}"[:500]
        return out

def describe()->dict[str,Any]:return PlanetaryAwareness().status()
