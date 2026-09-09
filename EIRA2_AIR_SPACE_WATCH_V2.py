from __future__ import annotations
import json, math, os, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

SCHEMA="eira2_air_space_watch_v2"
ROOT=Path("/media/domenicleonetti/easystore/EIRA/LIVE")
STATE=ROOT/"eira_probe"/"air_space_watch_v2"
TRACKS=STATE/"tracks"; EXPORTS=STATE/"exports"
for p in (STATE,TRACKS,EXPORTS): p.mkdir(parents=True,exist_ok=True)
TIMEOUT=20; MAX_ITEMS=250; MAX_HISTORY=2000
UA="EIRA2-Air-Space-Watch/2.0 (public-read-only; evidence-correlation)"

SOURCES={
 "opensky":{"kind":"aircraft_transponder","endpoint":"https://opensky-network.org/api/states/all","coverage_limited":True},
 "celestrak":{"kind":"orbital_catalog","endpoint":"https://celestrak.org/NORAD/elements/gp.php","minimum_refresh_seconds":7200},
 "cneos_fireballs":{"kind":"meteor_bolide","endpoint":"https://ssd-api.jpl.nasa.gov/fireball.api"},
 "cneos_sentry":{"kind":"neo_impact_monitoring","endpoint":"https://ssd-api.jpl.nasa.gov/sentry.api"},
 "aaro":{"kind":"official_uap_reference","url":"https://www.aaro.mil/UAP-Cases/Official-UAP-Imagery/","live_sensor_feed":False},
 "noaa_upper_air":{"kind":"balloon_upper_air_reference","url":"https://www.weather.gov/upperair/","live_balloon_track_guaranteed":False},
 "earth_observatory":{"kind":"shared_geospatial_spine","module":"eira2.evidence.earth_observatory_hazard_fusion"},
}
CLASS_ORDER=("known_aircraft","known_orbital_object","reentry_candidate","meteor_bolide","balloon_or_lighter_than_air_candidate","known_atmospheric_or_sensor_effect","unresolved_airborne_object")

def _get(url:str,params:dict[str,Any]|None=None,headers:dict[str,str]|None=None)->Any:
    if params: url+=("&" if "?" in url else "?")+urllib.parse.urlencode(params,doseq=True)
    h={"User-Agent":UA,"Accept":"application/json"}; h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def _finite(v:Any)->float|None:
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None

def _latlon(lat:Any,lon:Any)->tuple[float|None,float|None]:
    a,b=_finite(lat),_finite(lon)
    if a is None or b is None or not -90<=a<=90 or not -180<=b<=180: return None,None
    return a,b

def _norm_heading(v:Any)->float|None:
    x=_finite(v); return None if x is None else x%360.0

def _point_geometry(lat:Any,lon:Any,alt_m:Any=None)->dict[str,Any]|None:
    a,b=_latlon(lat,lon)
    if a is None:return None
    c=[b,a]; z=_finite(alt_m)
    if z is not None:c.append(z)
    return {"type":"Point","coordinates":c}

def _track(source:str,track_id:str,classification:str,lat:Any=None,lon:Any=None,
           geometric_altitude_m:Any=None,barometric_altitude_m:Any=None,
           velocity_mps:Any=None,heading_deg:Any=None,vertical_rate_mps:Any=None,
           observed_unix:Any=None,properties:dict[str,Any]|None=None,
           confidence:float|None=None,uncertainty:dict[str,Any]|None=None)->dict[str,Any]:
    lat,lon=_latlon(lat,lon); ga=_finite(geometric_altitude_m); ba=_finite(barometric_altitude_m)
    return {
      "schema":SCHEMA,"source":source,"track_id":str(track_id),"classification":classification,
      "latitude":lat,"longitude":lon,"geometric_altitude_m":ga,"barometric_altitude_m":ba,
      "geometry":_point_geometry(lat,lon,ga),"velocity_mps":_finite(velocity_mps),
      "heading_deg":_norm_heading(heading_deg),"vertical_rate_mps":_finite(vertical_rate_mps),
      "observed_unix":_finite(observed_unix),"retrieved_unix":time.time(),
      "properties":properties or {},"confidence":_finite(confidence),
      "uncertainty":uncertainty or {},"source_is_not_fact":True,
      "shared_geospatial_contract":"lon_lat_geojson; lat_lon_fields",
      "unresolved_does_not_mean_exotic":True,
    }

def _distance_km(a:dict[str,Any],b:dict[str,Any])->float|None:
    vals=(a.get("latitude"),a.get("longitude"),b.get("latitude"),b.get("longitude"))
    if any(v is None for v in vals):return None
    r=6371.0088;p1=math.radians(float(vals[0]));p2=math.radians(float(vals[2]))
    dp=p2-p1;dl=math.radians(((float(vals[3])-float(vals[1])+180)%360)-180)
    q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(min(1.0,math.sqrt(q)))

def _history_path(track_id:str)->Path:
    safe="".join(c for c in str(track_id) if c.isalnum() or c in "._-")[:128] or "unknown"
    return TRACKS/f"{safe}.jsonl"

def _record(track:dict[str,Any])->None:
    p=_history_path(track.get("track_id","unknown")); rows=[]
    if p.exists():
        try: rows=p.read_text(errors="replace").splitlines()[-(MAX_HISTORY-1):]
        except Exception: rows=[]
    rows.append(json.dumps(track,separators=(",",":"),ensure_ascii=False))
    tmp=p.with_suffix(".tmp");tmp.write_text("\n".join(rows)+"\n");os.replace(tmp,p)

def _kml_point(t:dict[str,Any])->str:
    if t.get("latitude") is None or t.get("longitude") is None:return ""
    alt=t.get("geometric_altitude_m"); z=float(alt) if alt is not None else 0.0
    mode="<altitudeMode>absolute</altitudeMode>" if alt is not None else "<altitudeMode>clampToGround</altitudeMode>"
    return f"<Point>{mode}<coordinates>{float(t['longitude']):.8f},{float(t['latitude']):.8f},{z:.2f}</coordinates></Point>"

class AirSpaceWatch:
    def status(self)->dict[str,Any]:
        return {"schema":SCHEMA,"root":str(STATE),"sources":SOURCES,"classification_order":CLASS_ORDER,
          "policy":{"public_read_only":True,"no_hardware_control":True,"no_interceptor_control":True,
          "no_classified_feed_claims":True,"no_weapon_targeting":True,"adsb_absence_is_not_proof":True,
          "unresolved_is_not_ufo":True,"independent_sensor_corroboration_for_strong_claims":True,
          "preserve_source_uncertainty":True,"track_history":True,"shared_earth_geospatial_spine":True,
          "google_earth_3d_tracks":True,"source_is_not_fact":True}}

    def aircraft(self,bbox:tuple[float,float,float,float]|None=None,limit:int=200,record:bool=False)->list[dict[str,Any]]:
        params={}
        if bbox:
            lamin,lomin,lamax,lomax=map(float,bbox)
            if not(-90<=lamin<=lamax<=90 and -180<=lomin<=lomax<=180):raise ValueError("invalid_bbox")
            params={"lamin":lamin,"lomin":lomin,"lamax":lamax,"lomax":lomax}
        headers={};token=os.getenv("OPENSKY_ACCESS_TOKEN")
        if token:headers["Authorization"]="Bearer "+token
        data=_get(SOURCES["opensky"]["endpoint"],params,headers);out=[]
        for s in (data.get("states") or [])[:max(1,min(int(limit),MAX_ITEMS))]:
            if not isinstance(s,list) or len(s)<17:continue
            t=_track("opensky",s[0] or "unknown","known_aircraft",s[6],s[5],
              geometric_altitude_m=s[13],barometric_altitude_m=s[7],velocity_mps=s[9],
              heading_deg=s[10],vertical_rate_mps=s[11],observed_unix=s[4] or s[3],
              properties={"icao24":s[0],"callsign":(s[1] or "").strip() or None,"origin_country":s[2],
              "on_ground":s[8],"squawk":s[14],"spi":s[15],"position_source":s[16],
              "last_contact_unix":s[4],"time_position_unix":s[3]},
              confidence=0.95,uncertainty={"coverage_limited":True,"transponder_dependent":True})
            out.append(t)
            if record:_record(t)
        return out

    def orbital_objects(self,group:str="active",limit:int=200)->list[dict[str,Any]]:
        allowed={"active","stations","visual","weather","resource","science","geo","gnss","starlink","oneweb","iridium-NEXT","decaying"}
        g=group if group in allowed else "active"
        data=_get(SOURCES["celestrak"]["endpoint"],{"GROUP":g,"FORMAT":"JSON"});out=[]
        for x in (data if isinstance(data,list) else [])[:max(1,min(int(limit),MAX_ITEMS))]:
            out.append(_track("celestrak",x.get("NORAD_CAT_ID") or x.get("OBJECT_ID") or x.get("OBJECT_NAME") or "unknown",
              "reentry_candidate" if g=="decaying" else "known_orbital_object",
              properties={"name":x.get("OBJECT_NAME"),"object_id":x.get("OBJECT_ID"),"norad_cat_id":x.get("NORAD_CAT_ID"),
              "epoch":x.get("EPOCH"),"mean_motion":x.get("MEAN_MOTION"),"eccentricity":x.get("ECCENTRICITY"),
              "inclination_deg":x.get("INCLINATION"),"ra_of_asc_node_deg":x.get("RA_OF_ASC_NODE"),
              "arg_of_pericenter_deg":x.get("ARG_OF_PERICENTER"),"mean_anomaly_deg":x.get("MEAN_ANOMALY")},
              confidence=0.9,uncertainty={"catalog_elements_not_current_position":True,"propagation_required_for_position":True}))
        return out

    def reentry_candidates(self,limit:int=100)->list[dict[str,Any]]:
        return self.orbital_objects("decaying",limit)

    def fireballs(self,limit:int=100)->list[dict[str,Any]]:
        data=_get(SOURCES["cneos_fireballs"]["endpoint"],{"limit":max(1,min(int(limit),MAX_ITEMS))})
        fields=data.get("fields") or [];out=[]
        for row in data.get("data") or []:
            x=dict(zip(fields,row));lat=_finite(x.get("lat"));lon=_finite(x.get("lon"))
            if lat is not None and str(x.get("lat-dir","")).upper()=="S":lat=-abs(lat)
            if lon is not None and str(x.get("lon-dir","")).upper()=="W":lon=-abs(lon)
            alt=_finite(x.get("alt"));vel=_finite(x.get("vel"))
            out.append(_track("cneos_fireballs",x.get("date") or len(out),"meteor_bolide",lat,lon,
              geometric_altitude_m=alt*1000 if alt is not None else None,
              velocity_mps=vel*1000 if vel is not None else None,properties=x,confidence=0.9,
              uncertainty={"reported_values_may_be_partial":True}))
        return out

    def sentry(self,limit:int=100)->list[dict[str,Any]]:
        rows=(_get(SOURCES["cneos_sentry"]["endpoint"]).get("data") or [])
        return [{"schema":SCHEMA,"source":"cneos_sentry","classification":"known_neo_impact_monitoring",
          "designation":x.get("des"),"fullname":x.get("fullname"),"impact_probability":x.get("ip"),
          "palermo_scale":x.get("ps_cum"),"torino_scale":x.get("ts_max"),"diameter_km":x.get("diameter"),
          "last_obs":x.get("last_obs"),"source_is_not_fact":True} for x in rows[:max(1,min(int(limit),MAX_ITEMS))]]

    def observation(self,observation:dict[str,Any])->dict[str,Any]:
        sensor=str(observation.get("sensor_type") or "unknown").lower()
        if sensor not in {"optical","infrared","radar","multilateration","visual","acoustic","other","unknown"}:sensor="other"
        t=_track(str(observation.get("source") or "external_observation"),observation.get("id","observation"),
          "unresolved_airborne_object",observation.get("latitude"),observation.get("longitude"),
          observation.get("geometric_altitude_m"),observation.get("barometric_altitude_m"),
          observation.get("velocity_mps"),observation.get("heading_deg"),observation.get("vertical_rate_mps"),
          observation.get("observed_unix"),{"sensor_type":sensor,"raw":observation.get("properties") or {}},
          confidence=observation.get("confidence"),uncertainty=observation.get("uncertainty") or {})
        _record(t);return t

    def correlate(self,observation:dict[str,Any],candidate_sets:dict[str,list[dict[str,Any]]] | None=None,
                  spatial_km:float=15,time_seconds:float=180)->dict[str,Any]:
        obs=self.observation(observation); candidate_sets=candidate_sets or {}; matches=[]
        for domain,rows in candidate_sets.items():
            for x in rows:
                d=_distance_km(obs,x)
                if d is None or d>float(spatial_km):continue
                dt=None
                if obs.get("observed_unix") is not None and x.get("observed_unix") is not None:
                    dt=abs(float(obs["observed_unix"])-float(x["observed_unix"]))
                    if dt>float(time_seconds):continue
                alt_delta=None;oa=obs.get("geometric_altitude_m");xa=x.get("geometric_altitude_m")
                if oa is not None and xa is not None:alt_delta=abs(float(oa)-float(xa))
                score=max(0.0,1.0-d/max(float(spatial_km),1e-9))
                if dt is not None:score*=max(0.0,1.0-dt/max(float(time_seconds),1e-9))
                matches.append({"domain":domain,"track":x,"distance_km":round(d,3),"time_delta_seconds":dt,
                                "altitude_delta_m":alt_delta,"match_score":round(score,4)})
        matches.sort(key=lambda z:z["match_score"],reverse=True);best=matches[0] if matches else None
        classification=(best["track"].get("classification") if best and best["match_score"]>=0.5 else "unresolved_airborne_object")
        return {"schema":SCHEMA,"observation":obs,"classification":classification,"best_candidate":best,
          "candidates":matches[:20],"confidence":"candidate_match_not_identity_proof" if best else "unresolved",
          "rules":{"adsb_absence_is_not_proof":True,"unresolved_does_not_mean_exotic":True,
          "independent_sensor_corroboration_required":True},"source_is_not_fact":True}

    def project_uncontrolled_descent(self,track:dict[str,Any],max_seconds:int=1800)->dict[str,Any]:
        lat,lon=_latlon(track.get("latitude"),track.get("longitude"));alt=_finite(track.get("geometric_altitude_m"))
        speed=_finite(track.get("velocity_mps"));hdg=_norm_heading(track.get("heading_deg"));vr=_finite(track.get("vertical_rate_mps"))
        if None in (lat,lon,alt,speed,hdg,vr):return {"ok":False,"reason":"insufficient_kinematics","source_is_not_fact":True}
        if vr>=0:return {"ok":False,"reason":"object_not_descending","source_is_not_fact":True}
        t=min(float(max_seconds),float(alt)/abs(float(vr)));ground=math.sqrt(max(0.0,float(speed)**2-float(vr)**2));dist=ground*t
        R=6371008.8;br=math.radians(float(hdg));p1=math.radians(float(lat));l1=math.radians(float(lon));ang=dist/R
        p2=math.asin(math.sin(p1)*math.cos(ang)+math.cos(p1)*math.sin(ang)*math.cos(br))
        l2=l1+math.atan2(math.sin(br)*math.sin(ang)*math.cos(p1),math.cos(ang)-math.sin(p1)*math.sin(p2))
        return {"ok":True,"model":"constant_velocity_screening_only","estimated_seconds":t,
          "estimated_ground_intersection":{"latitude":math.degrees(p2),"longitude":((math.degrees(l2)+180)%360)-180},
          "limitations":["natural_or_uncontrolled_objects_only","ignores_drag","ignores_lift","ignores_wind","ignores_maneuvering",
                         "not_for_weapon_targeting"],"source_is_not_fact":True}

    def track_history(self,track_id:str,limit:int=500)->list[dict[str,Any]]:
        p=_history_path(track_id)
        if not p.exists():return []
        out=[]
        for line in p.read_text(errors="replace").splitlines()[-max(1,min(int(limit),MAX_HISTORY)):]:
            try:out.append(json.loads(line))
            except Exception:pass
        return out

    def export_geojson(self,tracks:list[dict[str,Any]],filename:str="eira_air_space_tracks.geojson")->str:
        feats=[]
        for t in tracks:
            g=t.get("geometry")
            if isinstance(g,dict):feats.append({"type":"Feature","geometry":g,"properties":{k:v for k,v in t.items() if k!="geometry"}})
        p=EXPORTS/Path(filename).name;p.write_text(json.dumps({"type":"FeatureCollection","features":feats},indent=2))
        return str(p.relative_to(ROOT))

    def export_kml(self,tracks:list[dict[str,Any]],filename:str="eira_air_space_tracks.kml")->str:
        marks=[]
        for t in tracks:
            geom=_kml_point(t)
            if not geom:continue
            name=escape(str(t.get("properties",{}).get("callsign") or t.get("properties",{}).get("name") or t.get("track_id")))
            desc=escape(json.dumps({"classification":t.get("classification"),"source":t.get("source"),"confidence":t.get("confidence"),
                                   "uncertainty":t.get("uncertainty")},ensure_ascii=False)[:8000])
            marks.append(f"<Placemark><name>{name}</name><description>{desc}</description>{geom}</Placemark>")
        body='<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'+''.join(marks)+"</Document></kml>"
        p=EXPORTS/Path(filename).name;p.write_text(body);return str(p.relative_to(ROOT))

    def export_track_kml(self,track_id:str,filename:str|None=None)->str:
        rows=[x for x in self.track_history(track_id) if x.get("latitude") is not None and x.get("longitude") is not None]
        coords=[]
        for x in rows:
            z=x.get("geometric_altitude_m");coords.append(f"{float(x['longitude']):.8f},{float(x['latitude']):.8f},{float(z) if z is not None else 0.0:.2f}")
        name=escape(str(track_id));line=" ".join(coords)
        body=f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>{name}</name><LineString><altitudeMode>absolute</altitudeMode><coordinates>{line}</coordinates></LineString></Placemark></Document></kml>'
        p=EXPORTS/Path(filename or f"{track_id}.kml").name;p.write_text(body);return str(p.relative_to(ROOT))

    def official_reference_surfaces(self)->dict[str,Any]:
        return {"aaro":SOURCES["aaro"],"noaa_upper_air":SOURCES["noaa_upper_air"],
          "note":"Reference surfaces are not claimed as live machine-readable sensor feeds.","source_is_not_fact":True}

def describe()->dict[str,Any]:return AirSpaceWatch().status()
if __name__=="__main__":print(json.dumps(describe(),indent=2,sort_keys=True))
