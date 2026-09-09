from __future__ import annotations
import json, math, os, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

SCHEMA='eira2_air_space_watch_v1'
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
STATE=ROOT/'eira_probe'/'air_space_watch_v1'
STATE.mkdir(parents=True,exist_ok=True)
TIMEOUT=20
MAX_ITEMS=250
UA='EIRA2-Air-Space-Watch/1.0 (public-read-only; evidence-correlation)'

SOURCES={
 'opensky':{'kind':'aircraft','endpoint':'https://opensky-network.org/api/states/all','auth':'optional_oauth','public_limitations':True},
 'celestrak':{'kind':'orbital_objects','endpoint':'https://celestrak.org/NORAD/elements/gp.php','minimum_refresh_seconds':7200},
 'cneos_fireballs':{'kind':'meteor_bolide','endpoint':'https://ssd-api.jpl.nasa.gov/fireball.api','government_sensor_reports':True},
 'cneos_sentry':{'kind':'neo_impact_monitoring','endpoint':'https://ssd-api.jpl.nasa.gov/sentry.api'},
 'earth_observatory':{'kind':'shared_geospatial_evidence','module':'eira2.evidence.earth_observatory_hazard_fusion'},
}

def _get(url:str,params:dict[str,Any]|None=None,headers:dict[str,str]|None=None)->Any:
 if params: url+=('&' if '?' in url else '?')+urllib.parse.urlencode(params,doseq=True)
 h={'User-Agent':UA,'Accept':'application/json'}; h.update(headers or {})
 with urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=TIMEOUT) as r:
  return json.loads(r.read().decode('utf-8','replace'))

def _finite(v:Any)->float|None:
 try:
  x=float(v); return x if math.isfinite(x) else None
 except Exception:return None

def _latlon(lat:Any,lon:Any)->tuple[float|None,float|None]:
 a,b=_finite(lat),_finite(lon)
 if a is None or b is None or not(-90<=a<=90) or not(-180<=b<=180): return None,None
 return a,b

def _track(source:str,track_id:str,classification:str,lat:Any=None,lon:Any=None,alt_m:Any=None,velocity_mps:Any=None,heading_deg:Any=None,vertical_rate_mps:Any=None,observed_unix:Any=None,properties:dict[str,Any]|None=None,confidence:str='source_reported')->dict[str,Any]:
 lat,lon=_latlon(lat,lon)
 return {'schema':SCHEMA,'source':source,'track_id':str(track_id),'classification':classification,'latitude':lat,'longitude':lon,'altitude_m':_finite(alt_m),'velocity_mps':_finite(velocity_mps),'heading_deg':_finite(heading_deg),'vertical_rate_mps':_finite(vertical_rate_mps),'observed_unix':_finite(observed_unix),'retrieved_unix':time.time(),'properties':properties or {},'confidence':confidence,'source_is_not_fact':True,'unresolved_does_not_mean_exotic':True}

def _distance_km(a:dict[str,Any],b:dict[str,Any])->float|None:
 if None in (a.get('latitude'),a.get('longitude'),b.get('latitude'),b.get('longitude')):return None
 r=6371.0088; p1,p2=map(math.radians,[a['latitude'],b['latitude']]); dp=p2-p1; dl=math.radians(((b['longitude']-a['longitude']+180)%360)-180)
 q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 2*r*math.asin(min(1,math.sqrt(q)))

class AirSpaceWatch:
 def status(self)->dict[str,Any]:
  return {'schema':SCHEMA,'root':str(STATE),'sources':SOURCES,'policy':{'public_read_only':True,'no_hardware_control':True,'no_interceptor_control':True,'no_classified_feed_claims':True,'no_weapon_targeting':True,'no_identity_inference_from_missing_adsb':True,'unresolved_is_not_ufo':True,'preserve_source_uncertainty':True,'trajectory_is_estimate_not_fact':True,'google_earth_compatible_coordinates':True,'source_is_not_fact':True}}

 def aircraft(self,bbox:tuple[float,float,float,float]|None=None,limit:int=200)->list[dict[str,Any]]:
  params={}
  if bbox:
   lamin,lomin,lamax,lomax=map(float,bbox); params={'lamin':lamin,'lomin':lomin,'lamax':lamax,'lomax':lomax}
  headers={}; token=os.getenv('OPENSKY_ACCESS_TOKEN')
  if token: headers['Authorization']='Bearer '+token
  data=_get(SOURCES['opensky']['endpoint'],params,headers); out=[]
  for s in (data.get('states') or [])[:max(1,min(int(limit),MAX_ITEMS))]:
   if not isinstance(s,list) or len(s)<17:continue
   out.append(_track('opensky',s[0] or 'unknown','known_aircraft',s[6],s[5],s[13] if s[13] is not None else s[7],s[9],s[10],s[11],s[4] or s[3],{'icao24':s[0],'callsign':(s[1] or '').strip() or None,'origin_country':s[2],'on_ground':s[8],'squawk':s[14],'spi':s[15],'position_source':s[16],'last_contact_unix':s[4],'time_position_unix':s[3]}))
  return out

 def orbital_objects(self,group:str='active',limit:int=200)->list[dict[str,Any]]:
  allowed={'active','stations','visual','weather','resource','science','geo','gnss','starlink','oneweb','iridium-NEXT','decaying'}
  g=group if group in allowed else 'active'
  data=_get(SOURCES['celestrak']['endpoint'],{'GROUP':g,'FORMAT':'JSON'})
  out=[]
  for x in (data if isinstance(data,list) else [])[:max(1,min(int(limit),MAX_ITEMS))]:
   out.append(_track('celestrak',x.get('NORAD_CAT_ID') or x.get('OBJECT_ID') or x.get('OBJECT_NAME') or 'unknown','known_orbital_object',properties={'name':x.get('OBJECT_NAME'),'object_id':x.get('OBJECT_ID'),'norad_cat_id':x.get('NORAD_CAT_ID'),'epoch':x.get('EPOCH'),'mean_motion':x.get('MEAN_MOTION'),'eccentricity':x.get('ECCENTRICITY'),'inclination_deg':x.get('INCLINATION'),'ra_of_asc_node_deg':x.get('RA_OF_ASC_NODE'),'arg_of_pericenter_deg':x.get('ARG_OF_PERICENTER'),'mean_anomaly_deg':x.get('MEAN_ANOMALY'),'ephemeris_type':x.get('EPHEMERIS_TYPE')},confidence='catalog_orbit_elements'))
  return out

 def fireballs(self,limit:int=100)->list[dict[str,Any]]:
  data=_get(SOURCES['cneos_fireballs']['endpoint'],{'limit':max(1,min(int(limit),MAX_ITEMS))})
  fields=data.get('fields') or []; out=[]
  for row in data.get('data') or []:
   x=dict(zip(fields,row)); lat=_finite(x.get('lat')); lon=_finite(x.get('lon'))
   if lat is not None and str(x.get('lat-dir','')).upper()=='S':lat=-abs(lat)
   if lon is not None and str(x.get('lon-dir','')).upper()=='W':lon=-abs(lon)
   alt=_finite(x.get('alt')); vel=_finite(x.get('vel'))
   out.append(_track('cneos_fireballs',x.get('date') or len(out),'meteor_bolide',lat,lon,alt*1000 if alt is not None else None,vel*1000 if vel is not None else None,observed_unix=None,properties=x,confidence='government_sensor_report'))
  return out

 def sentry(self,limit:int=100)->list[dict[str,Any]]:
  data=_get(SOURCES['cneos_sentry']['endpoint']); rows=data.get('data') or []
  return [{'schema':SCHEMA,'source':'cneos_sentry','classification':'known_neo_impact_monitoring','designation':x.get('des'),'fullname':x.get('fullname'),'impact_probability':x.get('ip'),'palermo_scale':x.get('ps_cum'),'torino_scale':x.get('ts_max'),'diameter_km':x.get('diameter'),'last_obs':x.get('last_obs'),'source_is_not_fact':True} for x in rows[:max(1,min(int(limit),MAX_ITEMS))]]

 def correlate(self,observation:dict[str,Any],aircraft:list[dict[str,Any]]|None=None,spatial_km:float=10,time_seconds:float=120)->dict[str,Any]:
  obs=_track('external_observation',observation.get('id','observation'),'unresolved_airborne_object',observation.get('latitude'),observation.get('longitude'),observation.get('altitude_m'),observation.get('velocity_mps'),observation.get('heading_deg'),observation.get('vertical_rate_mps'),observation.get('observed_unix'),observation.get('properties',{}),'unresolved')
  candidates=[]
  for x in aircraft or []:
   d=_distance_km(obs,x)
   if d is None or d>float(spatial_km):continue
   dt=None
   if obs.get('observed_unix') is not None and x.get('observed_unix') is not None:dt=abs(obs['observed_unix']-x['observed_unix'])
   if dt is not None and dt>float(time_seconds):continue
   candidates.append({'track':x,'distance_km':round(d,3),'time_delta_seconds':dt})
  candidates.sort(key=lambda z:(z['distance_km'],z['time_delta_seconds'] if z['time_delta_seconds'] is not None else 1e99))
  classification='candidate_known_aircraft' if candidates else 'unresolved'
  return {'schema':SCHEMA,'observation':obs,'classification':classification,'candidates':candidates[:10],'rules':{'no_candidate_does_not_mean_ufo':True,'adsb_absence_is_not_proof':True,'independent_sensor_corroboration_required_for_strong_claims':True},'source_is_not_fact':True}

 def project_ballistic_ground_intersection(self,track:dict[str,Any],max_seconds:int=1800,step_seconds:int=1)->dict[str,Any]:
  # Generic physics estimate for natural/uncontrolled descending objects only; not weapon guidance.
  lat,lon=_latlon(track.get('latitude'),track.get('longitude')); alt=_finite(track.get('altitude_m')); speed=_finite(track.get('velocity_mps')); hdg=_finite(track.get('heading_deg')); vr=_finite(track.get('vertical_rate_mps'))
  if None in (lat,lon,alt,speed,hdg,vr):return {'ok':False,'reason':'insufficient_kinematics','source_is_not_fact':True}
  if vr>=0:return {'ok':False,'reason':'object_not_descending','source_is_not_fact':True}
  t=min(float(max_seconds),alt/abs(vr)); ground_speed=math.sqrt(max(0.0,speed*speed-vr*vr)); distance_m=ground_speed*t
  R=6371008.8; br=math.radians(hdg); p1=math.radians(lat); l1=math.radians(lon); ang=distance_m/R
  p2=math.asin(math.sin(p1)*math.cos(ang)+math.cos(p1)*math.sin(ang)*math.cos(br)); l2=l1+math.atan2(math.sin(br)*math.sin(ang)*math.cos(p1),math.cos(ang)-math.sin(p1)*math.sin(p2))
  return {'ok':True,'model':'constant_velocity_straight_line_screening_only','estimated_seconds':t,'estimated_ground_intersection':{'latitude':math.degrees(p2),'longitude':((math.degrees(l2)+180)%360)-180},'limitations':['ignores_drag','ignores_lift','ignores_wind','ignores_maneuvering','not_for_weapon_targeting'],'source_is_not_fact':True}

def describe()->dict[str,Any]:return AirSpaceWatch().status()
if __name__=='__main__':print(json.dumps(describe(),indent=2,sort_keys=True))
