from __future__ import annotations

import hashlib, json, os, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SCHEMA="eira2_open_book_oai_harvester_v1"
ROOT=Path(os.environ.get("EIRA_LIVE_ROOT","/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
STATE=ROOT/"eira_probe"/"universe_library"/"open_book_oai_state.json"
UA="EIRA2-Universe-Library/2.0 lawful OAI harvester"
SOURCES={
 "doab":{"base":"https://directory.doabooks.org/oai/request","prefix":"oai_dc","kind":"peer_reviewed_open_access_books"},
 "bhl":{"base":"https://www.biodiversitylibrary.org/oai","prefix":"oai_dc","kind":"biodiversity_literature"},
}
NS={"oai":"http://www.openarchives.org/OAI/2.0/","dc":"http://purl.org/dc/elements/1.1/","oai_dc":"http://www.openarchives.org/OAI/2.0/oai_dc/"}

def _atomic(obj:dict[str,Any])->None:
 STATE.parent.mkdir(parents=True,exist_ok=True); t=STATE.with_name(STATE.name+f".tmp.{os.getpid()}"); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n"); os.replace(t,STATE)

def _get(url:str,timeout:int=120)->bytes:
 req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/xml"})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

def _vals(meta:ET.Element,tag:str)->list[str]:
 return [str(x.text or "").strip() for x in meta.findall(f".//dc:{tag}",NS) if str(x.text or "").strip()]

def harvest(source_name:str,max_pages:int|None=None)->dict[str,Any]:
 if source_name not in SOURCES:raise ValueError("unknown_source")
 from eira2.evidence.universe_public_library import PublicLibraryVault
 cfg=SOURCES[source_name]; token=""; pages=records=inserted=updated=unchanged=deleted=0; started=time.time()
 with PublicLibraryVault() as vault:
  while True:
   if token:
    q=urllib.parse.urlencode({"verb":"ListRecords","resumptionToken":token})
   else:
    q=urllib.parse.urlencode({"verb":"ListRecords","metadataPrefix":cfg["prefix"]})
   root=ET.fromstring(_get(cfg["base"]+"?"+q)); pages+=1; now=time.time()
   for rec in root.findall(".//oai:record",NS):
    header=rec.find("oai:header",NS)
    if header is None:continue
    ident=(header.findtext("oai:identifier",default="",namespaces=NS) or "").strip()
    if not ident:continue
    if header.get("status")=="deleted":deleted+=1;continue
    meta=rec.find("oai:metadata",NS)
    if meta is None:continue
    titles=_vals(meta,"title"); creators=_vals(meta,"creator"); subjects=_vals(meta,"subject"); langs=_vals(meta,"language"); rights=_vals(meta,"rights"); ids=_vals(meta,"identifier"); dates=_vals(meta,"date")
    obj={"oai_identifier":ident,"titles":titles,"creators":creators,"subjects":subjects,"languages":langs,"rights":rights,"identifiers":ids,"dates":dates}
    mj=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":")); mh=hashlib.sha256(mj.encode()).hexdigest(); url=next((x for x in ids if x.startswith("http")),"")
    old=vault.db.execute("SELECT metadata_hash FROM works WHERE source_name=? AND source_work_id=?",(source_name,ident)).fetchone()
    if old is None:
     vault.db.execute("INSERT INTO works(source_name,source_work_id,title,authors,subjects,language,source_url,source_release_date,rights,metadata_json,metadata_hash,first_seen_unix,last_seen_unix) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(source_name,ident,"; ".join(titles),"; ".join(creators),"; ".join(subjects),"; ".join(langs),url,"; ".join(dates),"; ".join(rights),mj,mh,now,now));inserted+=1
    elif old[0]!=mh:
     vault.db.execute("UPDATE works SET title=?,authors=?,subjects=?,language=?,source_url=?,source_release_date=?,rights=?,metadata_json=?,metadata_hash=?,last_seen_unix=? WHERE source_name=? AND source_work_id=?",("; ".join(titles),"; ".join(creators),"; ".join(subjects),"; ".join(langs),url,"; ".join(dates),"; ".join(rights),mj,mh,now,source_name,ident));updated+=1
    else:
     vault.db.execute("UPDATE works SET last_seen_unix=? WHERE source_name=? AND source_work_id=?",(now,source_name,ident));unchanged+=1
    records+=1
   tok=root.find(".//oai:resumptionToken",NS); token=(tok.text or "").strip() if tok is not None else ""
   _atomic({"schema":SCHEMA,"source":source_name,"status":"HARVESTING" if token else "COMPLETE","pages":pages,"records":records,"inserted":inserted,"updated":updated,"unchanged":unchanged,"deleted_seen":deleted,"resumption_token":token,"updated_unix":time.time()})
   if not token or (max_pages is not None and pages>=max_pages):break
 result={"schema":SCHEMA,"source":source_name,"ok":True,"complete":not bool(token),"pages":pages,"records":records,"inserted":inserted,"updated":updated,"unchanged":unchanged,"deleted_seen":deleted,"started_unix":started,"completed_unix":time.time(),"metadata_only_until_item_license_and_direct_fulltext_are_verified":True,"source_is_not_fact":True};_atomic(result);return result

def harvest_all()->dict[str,Any]:
 out={};ok=True
 for s in SOURCES:
  try:out[s]=harvest(s)
  except Exception as e:out[s]={"ok":False,"error":f"{type(e).__name__}:{e}"};ok=False
 return {"schema":SCHEMA+"_all","ok":ok,"sources":out,"source_is_not_fact":True}

def self_test()->dict[str,Any]:
 c={"doab":SOURCES["doab"]["base"].startswith("https://"),"bhl":SOURCES["bhl"]["base"].startswith("https://"),"source_count":len(SOURCES)==2,"state":STATE.name.endswith(".json")};return {"schema":SCHEMA+"_self_test","ok":all(c.values()),"checks":c}
if __name__=="__main__":
 import argparse
 p=argparse.ArgumentParser();p.add_argument("--source",choices=list(SOURCES));p.add_argument("--all",action="store_true");p.add_argument("--max-pages",type=int);a=p.parse_args()
 r=harvest_all() if a.all else (harvest(a.source,a.max_pages) if a.source else self_test());print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r.get("ok") else 1)
