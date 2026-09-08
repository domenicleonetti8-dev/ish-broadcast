#!/usr/bin/env python3
from __future__ import annotations
import json,hashlib,sys
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
sys.path.insert(0,str(ROOT))
from eira2.operations.model_takeover import REQUIRED_MODELS,_model_manifest_path,_manifest_payload,_manifest_digests,_blob_path

def sha(p:Path):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()

def main():
 asset_p=ROOT/'var'/'eira2-private-model-assets.json'; cont_p=ROOT/'var'/'eira2-private-model-containment.json'
 out={'schema':'eira2_model_attestation_fastcheck_forensic_v1','ok':False,'mutates_live':False}
 try:
  asset=json.loads(asset_p.read_text()); cont=json.loads(cont_p.read_text())
  model_root=Path(str(cont.get('model_store') or ROOT/'var'/'models'/'ollama')).resolve()
  rows=[]; unique={}
  for model in REQUIRED_MODELS:
   man=_model_manifest_path(model_root,model); payload=_manifest_payload(man,model); digests=_manifest_digests(payload,model)
   blobs=[]
   for d in digests:
    p=_blob_path(model_root,d); st=p.stat(); unique[d]=st.st_size; blobs.append({'digest':d,'size':st.st_size,'is_file':p.is_file(),'is_symlink':p.is_symlink()})
   rows.append({'model':model,'manifest':str(man),'manifest_sha256':sha(man),'blob_count':len(digests),'blobs':blobs})
  out.update({'asset_receipt':asset,'containment_receipt':cont,'model_root':str(model_root),'models':rows,'unique_blob_count':len(unique),'unique_blob_bytes':sum(unique.values()),'ok':asset.get('ok') is True and asset.get('all_manifest_referenced_blobs_hash_verified') is True and cont.get('ok') is True})
 except Exception as exc: out['error']=f'{type(exc).__name__}:{exc}'
 print(json.dumps(out,separators=(',',':'))); return 0 if out['ok'] else 1
if __name__=='__main__': raise SystemExit(main())
