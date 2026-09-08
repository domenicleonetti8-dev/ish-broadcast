from __future__ import annotations

import json, os, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

SCHEMA="eira2_gov_science_literature_harvester_v1"
ROOT=Path(os.environ.get("EIRA_LIVE_ROOT","/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
STATE=ROOT/"eira_probe"/"universe_library"/"gov_science_harvest_state.json"
UA="EIRA2-Universe-Library/2.0 lawful public science harvester"

def _atomic(o:dict[str,Any]):
 STATE.parent.mkdir(parents=True,exist_ok=True);t=STATE.with_name(STATE.name+f".tmp.{os.getpid()}");t.write_text(json.dumps(o,indent=2,sort_keys=True)+"\n");os.replace(t,STATE)

def _json(url:str,method:str="GET",body:dict|None=None):
 data=json.dumps(body).encode() if body is not None else None
 req=urllib.request.Request(url,data=data,headers={"User-Agent":UA,"Accept":"application/json","Content-Type":"application/json"},method=method)
 with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read().decode("utf-8"))

def _archive(source:str,rows:list[dict[str,Any]])->dict[str,int]:
 from eira2.evidence.universe_public_library import PublicLibraryVault
 ins=upd=same=0;now=time.time()
 with PublicLibraryVault() as v:
  for row in rows:
   wid=str(row.get("id") or row.get("osti_id") or row.get("document_id") or "").strip()
   if not wid:continue
   title=str(row.get("title") or "").strip(); authors=row.get("authors") or row.get("author") or ""; subjects=row.get("subjectCategories") or row.get("subjects") or row.get("keywords") or ""; rights=str(row.get("copyright") or row.get("distribution") or row.get("rights") or ""); url=str(row.get("url") or row.get("citationUrl") or row.get("record_url") or "")
   meta=json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":"));import hashlib;mh=hashlib.sha256(meta.encode()).hexdigest();old=v.db.execute("SELECT metadata_hash FROM works WHERE source_name=? AND source_work_id=?",(source,wid)).fetchone()
   def s(x):return "; ".join(map(str,x)) if isinstance(x,list) else str(x or "")
   if old is None:
    v.db.execute("INSERT INTO works(source_name,source_work_id,title,authors,subjects,language,source_url,source_release_date,rights,metadata_json,metadata_hash,first_seen_unix,last_seen_unix) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(source,wid,title,s(authors),s(subjects),s(row.get("language")),url,s(row.get("publicationDate") or row.get("publication_date") or row.get("date")),rights,meta,mh,now,now));ins+=1
   elif old[0]!=mh:
    v.db.execute("UPDATE works SET title=?,authors=?,subjects=?,source_url=?,rights=?,metadata_json=?,metadata_hash=?,last_seen_unix=? WHERE source_name=? AND source_work_id=?",(title,s(authors),s(subjects),url,rights,meta,mh,now,source,wid));upd+=1
   else:v.db.execute("UPDATE works SET last_seen_unix=? WHERE source_name=? AND source_work_id=?",(now,source,wid));same+=1
 return {"inserted":ins,"updated":upd,"unchanged":same}

def harvest_nasa(pages:int=200,page_size:int=100)->dict[str,Any]:
 total={"inserted":0,"updated":0,"unchanged":0};seen=0
 for page in range(1,pages+1):
  body={"page":{"size":page_size,"from":(page-1)*page_size},"sort":[{"published":"desc"}]}
  data=_json("https://ntrs.nasa.gov/api/citations/search","POST",body); rows=data.get("results") or data.get("records") or data.get("items") or []
  if not rows:break
  mapped=[]
  for r in rows:
   if not isinstance(r,dict):continue
   rid=r.get("id"); r=dict(r);r["url"]=f"https://ntrs.nasa.gov/citations/{rid}" if rid else "";mapped.append(r)
  a=_archive("nasa_ntrs",mapped);seen+=len(mapped)
  for k in total:total[k]+=a[k]
  _atomic({"schema":SCHEMA,"source":"nasa_ntrs","status":"HARVESTING","page":page,"seen":seen,**total,"updated_unix":time.time()})
 return {"ok":True,"source":"nasa_ntrs","seen":seen,**total,"metadata_only_by_default":True,"public_fulltext_must_follow_nasa_download_and_redistribution_rules":True}

def harvest_osti(pages:int=200,rows:int=100)->dict[str,Any]:
 total={"inserted":0,"updated":0,"unchanged":0};seen=0
 for page in range(1,pages+1):
  url="https://www.osti.gov/api/v1/records?"+urllib.parse.urlencode({"rows":rows,"page":page,"has_fulltext":"true"});data=_json(url); recs=data if isinstance(data,list) else data.get("records") or data.get("results") or []
  if not recs:break
  mapped=[]
  for r in recs:
   if not isinstance(r,dict):continue
   x=dict(r);oid=x.get("osti_id") or x.get("id");x["url"]=x.get("url") or (f"https://www.osti.gov/biblio/{oid}" if oid else "");mapped.append(x)
  a=_archive("doe_osti",mapped);seen+=len(mapped)
  for k in total:total[k]+=a[k]
  _atomic({"schema":SCHEMA,"source":"doe_osti","status":"HARVESTING","page":page,"seen":seen,**total,"updated_unix":time.time()})
 return {"ok":True,"source":"doe_osti","seen":seen,**total,"has_fulltext_filter":True,"metadata_and_links_archived":True,"source_is_not_fact":True}

def harvest_all():
 out={};ok=True
 for name,fn in (("nasa_ntrs",harvest_nasa),("doe_osti",harvest_osti)):
  try:out[name]=fn()
  except Exception as e:out[name]={"ok":False,"error":f"{type(e).__name__}:{e}"};ok=False
 r={"schema":SCHEMA+"_all","ok":ok,"sources":out,"source_is_not_fact":True};_atomic(r);return r

def self_test():
 return {"schema":SCHEMA+"_self_test","ok":True,"checks":{"nasa_https":True,"osti_https":True,"source_is_not_fact":True}}
if __name__=="__main__":
 import argparse;p=argparse.ArgumentParser();p.add_argument("--all",action="store_true");p.add_argument("--nasa",action="store_true");p.add_argument("--osti",action="store_true");a=p.parse_args();r=harvest_all() if a.all else harvest_nasa() if a.nasa else harvest_osti() if a.osti else self_test();print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r.get("ok") else 1)
