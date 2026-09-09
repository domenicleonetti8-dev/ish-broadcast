#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sqlite3, tarfile, tempfile, time
from pathlib import Path

ROOT=Path(os.environ.get('EIRA_LIVE_ROOT','/media/domenicleonetti/easystore/EIRA/LIVE')).resolve()
VAULT=ROOT/'eira_probe/universe_library/source_vault'
DB=VAULT/'source_index.sqlite3'
SEEDS=ROOT/'eira_probe/universe_library/dormant_seeds'
WORK=ROOT/'eira_probe/universe_library/awakened'
SCHEMA='eira2_dormant_library_seed_v1'
CHUNK=8*1024*1024

def sha_file(p, chunk=1024*1024):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(chunk),b''): h.update(b)
 return h.hexdigest()

def atomic_json(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+'.tmp'); t.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); os.replace(t,p)

def safe_rel(s):
 p=(VAULT/s).resolve()
 if p!=VAULT and VAULT not in p.parents: raise ValueError('outside_vault')
 return p

def classify(source):
 return 'textbook' if source=='openstax' else 'book'

def eligible_rows():
 if not DB.is_file(): return []
 db=sqlite3.connect(str(DB)); db.row_factory=sqlite3.Row
 rows=db.execute('''SELECT d.document_hash,d.source_name,d.source_work_id,d.relative_path,d.bytes,w.title,w.authors,w.subjects,w.language,w.source_url,w.rights,w.metadata_json FROM documents d LEFT JOIN works w ON w.source_name=d.source_name AND w.source_work_id=d.source_work_id ORDER BY d.source_name,d.source_work_id,d.relative_path''').fetchall(); db.close()
 out=[]
 for r in rows:
  source=r['source_name']; rights=(r['rights'] or '').lower(); p=safe_rel(r['relative_path'])
  if not p.is_file(): continue
  if source=='project_gutenberg': allowed=True
  elif source=='openstax': allowed=any(x in rights for x in ('creative commons','cc by','cc-by','open license','openstax'))
  else: allowed=False
  if not allowed: continue
  out.append(dict(r)|{'path':str(p),'kind':classify(source)})
 return out

def make_seed(row, retire=False):
 src=Path(row['path']); sid=f"{row['source_name']}__{row['source_work_id']}__{row['document_hash'][:16]}".replace('/','_').replace(':','_')
 dst=SEEDS/row['kind']/sid; dst.mkdir(parents=True,exist_ok=True)
 manifest=dst/'manifest.json'
 if manifest.is_file():
  old=json.loads(manifest.read_text())
  if old.get('source_sha256')==sha_file(src) and old.get('verified') is True: return old|{'already_seeded':True}
 with tempfile.TemporaryDirectory(prefix='eira_seed_') as td:
  archive=Path(td)/'payload.tar.gz'
  with tarfile.open(archive,'w:gz') as tf: tf.add(src,arcname=src.name,recursive=False)
  archive_sha=sha_file(archive); parts=[]
  with archive.open('rb') as f:
   i=0
   while True:
    b=f.read(CHUNK)
    if not b: break
    name=f'chunk_{i:06d}.bin'; q=dst/name; q.write_bytes(b); parts.append({'name':name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}); i+=1
  rejoined=Path(td)/'verify.tar.gz'
  with rejoined.open('wb') as o:
   for part in parts:
    q=dst/part['name']; b=q.read_bytes()
    if hashlib.sha256(b).hexdigest()!=part['sha256']: raise RuntimeError('chunk_hash_mismatch')
    o.write(b)
  if sha_file(rejoined)!=archive_sha: raise RuntimeError('archive_reassembly_hash_mismatch')
  verify_dir=Path(td)/'verify_extract'; verify_dir.mkdir()
  with tarfile.open(rejoined,'r:gz') as tf: tf.extractall(verify_dir)
  vp=verify_dir/src.name
  source_sha=sha_file(src)
  if not vp.is_file() or sha_file(vp)!=source_sha: raise RuntimeError('extracted_source_hash_mismatch')
  obj={'schema':SCHEMA,'seed_id':sid,'kind':row['kind'],'source_name':row['source_name'],'source_work_id':row['source_work_id'],'title':row.get('title') or '','authors':row.get('authors') or '','subjects':row.get('subjects') or '','language':row.get('language') or '','source_url':row.get('source_url') or '','rights':row.get('rights') or '','source_relative_path':row['relative_path'],'source_bytes':src.stat().st_size,'source_sha256':source_sha,'archive_sha256':archive_sha,'archive_bytes':archive.stat().st_size,'chunk_bytes':CHUNK,'chunk_count':len(parts),'chunks':parts,'compression':'tar.gz','verified':True,'dormant':True,'created_unix':time.time(),'retired_expanded_source':False}
  atomic_json(manifest,obj)
  if retire:
   retired=ROOT/'eira_probe/universe_library/retired_expanded'/row['relative_path']; retired.parent.mkdir(parents=True,exist_ok=True); os.replace(src,retired); obj['retired_expanded_source']=True; obj['retired_path']=str(retired.relative_to(ROOT)); atomic_json(manifest,obj)
  return obj

def seed_all(retire=False, limit=None):
 rows=eligible_rows();
 if limit is not None: rows=rows[:limit]
 results=[]; before=sum(Path(r['path']).stat().st_size for r in rows if Path(r['path']).is_file())
 for r in rows:
  try: results.append({'ok':True,'seed':make_seed(r,retire)})
  except Exception as e: results.append({'ok':False,'source':r['relative_path'],'error':f'{type(e).__name__}:{e}'})
 after=sum(x['seed'].get('archive_bytes',0) for x in results if x.get('ok'))
 out={'schema':SCHEMA+'_batch','ok':all(x.get('ok') for x in results),'eligible':len(rows),'seeded':sum(1 for x in results if x.get('ok')),'source_bytes':before,'compressed_bytes':after,'retire':retire,'results':results,'unix':time.time()}; atomic_json(SEEDS/'latest_batch.json',out); return out

def awaken(seed_id):
 matches=list(SEEDS.rglob(seed_id+'/manifest.json'))
 if len(matches)!=1: raise RuntimeError('seed_not_unique_or_missing')
 m=json.loads(matches[0].read_text()); dst=WORK/seed_id; dst.mkdir(parents=True,exist_ok=True); archive=dst/'payload.tar.gz'
 with archive.open('wb') as o:
  for part in m['chunks']:
   q=matches[0].parent/part['name']; b=q.read_bytes()
   if hashlib.sha256(b).hexdigest()!=part['sha256']: raise RuntimeError('chunk_hash_mismatch')
   o.write(b)
 if sha_file(archive)!=m['archive_sha256']: raise RuntimeError('archive_hash_mismatch')
 with tarfile.open(archive,'r:gz') as tf: tf.extractall(dst)
 return {'ok':True,'seed_id':seed_id,'path':str(dst),'unix':time.time()}

if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--seed-all',action='store_true'); ap.add_argument('--retire',action='store_true'); ap.add_argument('--limit',type=int); ap.add_argument('--awaken'); a=ap.parse_args()
 if a.awaken: out=awaken(a.awaken)
 else: out=seed_all(retire=a.retire,limit=a.limit)
 print(json.dumps(out,indent=2,sort_keys=True))
