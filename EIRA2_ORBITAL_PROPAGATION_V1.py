from __future__ import annotations
import datetime as dt, math, time
from typing import Any

SCHEMA="eira2_orbital_propagation_v1"
MU_KM3_S2=398600.4418
EARTH_RADIUS_KM=6378.137
EARTH_FLATTENING=1/298.257223563

try:
    from sgp4.api import Satrec, jday
    from sgp4 import omm as sgp4_omm
    HAVE_SGP4=True
except Exception:
    Satrec=None; jday=None; sgp4_omm=None; HAVE_SGP4=False


def _finite(v:Any)->float|None:
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None


def _parse_epoch(v:Any)->dt.datetime|None:
    if not v:return None
    s=str(v).strip().replace("Z","+00:00")
    try:
        x=dt.datetime.fromisoformat(s)
        if x.tzinfo is None:x=x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(dt.timezone.utc)
    except Exception:return None


def _gmst_rad(unix:float)->float:
    jd=unix/86400.0+2440587.5
    t=(jd-2451545.0)/36525.0
    deg=280.46061837+360.98564736629*(jd-2451545.0)+0.000387933*t*t-(t*t*t)/38710000.0
    return math.radians(deg%360.0)


def _eci_to_geodetic(x:float,y:float,z:float,unix:float)->tuple[float,float,float]:
    th=_gmst_rad(unix)
    xe=x*math.cos(th)+y*math.sin(th)
    ye=-x*math.sin(th)+y*math.cos(th)
    ze=z
    lon=math.atan2(ye,xe)
    a=EARTH_RADIUS_KM; f=EARTH_FLATTENING; e2=f*(2-f)
    p=math.hypot(xe,ye)
    lat=math.atan2(ze,p*(1-e2))
    for _ in range(8):
        s=math.sin(lat); n=a/math.sqrt(1-e2*s*s)
        alt=p/max(math.cos(lat),1e-12)-n
        lat=math.atan2(ze,p*(1-e2*n/(n+alt)))
    s=math.sin(lat); n=a/math.sqrt(1-e2*s*s)
    alt=p/max(math.cos(lat),1e-12)-n
    return math.degrees(lat),((math.degrees(lon)+180)%360)-180,alt


def _kepler_E(m:float,e:float)->float:
    e=max(0.0,min(float(e),0.999999)); x=m
    for _ in range(20):
        f=x-e*math.sin(x)-m; d=1-e*math.cos(x)
        step=f/max(abs(d),1e-12)
        x-=step
        if abs(step)<1e-12:break
    return x


def _two_body_eci(omm:dict[str,Any],unix:float)->tuple[float,float,float]|None:
    epoch=_parse_epoch(omm.get("EPOCH")); mm=_finite(omm.get("MEAN_MOTION")); ecc=_finite(omm.get("ECCENTRICITY"))
    inc=_finite(omm.get("INCLINATION")); raan=_finite(omm.get("RA_OF_ASC_NODE")); argp=_finite(omm.get("ARG_OF_PERICENTER")); ma=_finite(omm.get("MEAN_ANOMALY"))
    if epoch is None or None in (mm,ecc,inc,raan,argp,ma) or mm<=0:return None
    n=float(mm)*2*math.pi/86400.0
    a=(MU_KM3_S2/(n*n))**(1/3)
    m=(math.radians(float(ma))+n*(unix-epoch.timestamp()))%(2*math.pi)
    E=_kepler_E(m,float(ecc))
    xpf=a*(math.cos(E)-float(ecc)); ypf=a*math.sqrt(max(0.0,1-float(ecc)**2))*math.sin(E)
    O=math.radians(float(raan)); i=math.radians(float(inc)); w=math.radians(float(argp))
    cw,sw,cO,sO,ci,si=math.cos(w),math.sin(w),math.cos(O),math.sin(O),math.cos(i),math.sin(i)
    x=(cO*cw-sO*sw*ci)*xpf+(-cO*sw-sO*cw*ci)*ypf
    y=(sO*cw+cO*sw*ci)*xpf+(-sO*sw+cO*cw*ci)*ypf
    z=(sw*si)*xpf+(cw*si)*ypf
    return x,y,z


def _sgp4_eci(omm:dict[str,Any],unix:float)->tuple[float,float,float]|None:
    if not HAVE_SGP4:return None
    try:
        sat=Satrec(); sgp4_omm.initialize(sat,{k:str(v) for k,v in omm.items() if v is not None})
        t=dt.datetime.fromtimestamp(unix,dt.timezone.utc)
        jd,fr=jday(t.year,t.month,t.day,t.hour,t.minute,t.second+t.microsecond/1e6)
        err,r,_v=sat.sgp4(jd,fr)
        if err!=0:return None
        return float(r[0]),float(r[1]),float(r[2])
    except Exception:return None


class OrbitalPropagationEngine:
    def status(self)->dict[str,Any]:
        return {"schema":SCHEMA,"sgp4_available":HAVE_SGP4,"preferred_model":"SGP4" if HAVE_SGP4 else "two_body_screening_fallback",
                "policy":{"source_is_not_fact":True,"fallback_is_not_sgp4":True,"reentry_corridor_is_screening_not_impact_prediction":True,
                          "no_weapon_targeting":True,"public_read_only":True}}

    def propagate_omm(self,omm:dict[str,Any],unix:float|None=None)->dict[str,Any]:
        unix=float(unix if unix is not None else time.time())
        r=_sgp4_eci(omm,unix); model="SGP4" if r is not None else "two_body_screening_fallback"
        if r is None:r=_two_body_eci(omm,unix)
        if r is None:return {"ok":False,"schema":SCHEMA,"reason":"insufficient_or_invalid_omm","source_is_not_fact":True}
        lat,lon,alt_km=_eci_to_geodetic(*r,unix)
        epoch=_parse_epoch(omm.get("EPOCH")); age=abs(unix-epoch.timestamp()) if epoch else None
        uncertainty_km=(5.0 if model=="SGP4" else 50.0)+(0.0005*(age or 0.0) if model=="SGP4" else 0.003*(age or 0.0))
        return {"ok":True,"schema":SCHEMA,"model":model,"unix":unix,"latitude":lat,"longitude":lon,"geometric_altitude_m":alt_km*1000,
                "uncertainty_radius_km":round(min(5000.0,uncertainty_km),3),"epoch_age_seconds":age,
                "norad_cat_id":omm.get("NORAD_CAT_ID"),"name":omm.get("OBJECT_NAME"),"source_is_not_fact":True,
                "limitations":[] if model=="SGP4" else ["not_sgp4","ignores_J2_and_drag","screening_only"]}

    def ground_track(self,omm:dict[str,Any],start_unix:float|None=None,duration_seconds:int=5400,step_seconds:int=60)->dict[str,Any]:
        start=float(start_unix if start_unix is not None else time.time()); step=max(10,min(int(step_seconds),600)); dur=max(step,min(int(duration_seconds),21600))
        pts=[]
        for t in range(0,dur+1,step):
            p=self.propagate_omm(omm,start+t)
            if p.get("ok"):pts.append({"unix":p["unix"],"latitude":p["latitude"],"longitude":p["longitude"],"geometric_altitude_m":p["geometric_altitude_m"],"uncertainty_radius_km":p["uncertainty_radius_km"],"model":p["model"]})
        return {"schema":SCHEMA,"points":pts,"source_is_not_fact":True}

    def reentry_screening_corridor(self,omm:dict[str,Any],center_unix:float|None=None,window_seconds:int=1800,step_seconds:int=60)->dict[str,Any]:
        center=float(center_unix if center_unix is not None else time.time()); window=max(300,min(int(window_seconds),10800)); step=max(20,min(int(step_seconds),300))
        pts=[]
        for off in range(-window,window+1,step):
            p=self.propagate_omm(omm,center+off)
            if p.get("ok"):
                # Reentry uncertainty intentionally widens aggressively because atmospheric drag/breakup are not modeled.
                drag_unc=max(100.0,float(p["uncertainty_radius_km"])+abs(off)*0.15)
                pts.append({"unix":p["unix"],"latitude":p["latitude"],"longitude":p["longitude"],"altitude_m":p["geometric_altitude_m"],"uncertainty_radius_km":round(min(5000.0,drag_unc),3)})
        return {"schema":SCHEMA,"kind":"reentry_ground_track_screening_corridor","points":pts,
                "limitations":["not_atmospheric_entry_simulation","no_breakup_model","no_ballistic_coefficient_solution","not_ground_impact_prediction","not_for_weapon_targeting"],
                "source_is_not_fact":True}

def describe()->dict[str,Any]:return OrbitalPropagationEngine().status()
