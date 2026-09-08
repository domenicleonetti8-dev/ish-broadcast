#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path('/media/domenicleonetti/easystore/EIRA/LIVE')
TARGET=ROOT/'eira2/operations/model_takeover.py'
EXPECTED='a0245e1e13c3c5b62fadec312c887dbd1bc2bf8770ba53957e3d2b1980b6ba7b'
REPO=ROOT/'eira_probe/transport_runtime_v6/repo'
GEN='.eira2_generated/model_fast_boot_v1/model_takeover.py'
HELPER=r'''

def verify_model_store_boot_attested(*, runtime_root: Path, root: Path, models: Sequence[str] = REQUIRED_MODELS) -> dict[str, object]:
    """Fast boot verification against the last full cryptographic takeover attestation.

    This does not claim to re-hash multi-gigabyte blobs on every boot. It requires a
    prior full-hash asset receipt, unchanged model manifests, the exact required model
    set, content-addressed blob paths, non-symlink regular files, and the attested
    aggregate blob count/byte count. Full byte hashing remains in verify_model_store().
    """
    runtime_root = runtime_root.expanduser().resolve()
    root = root.expanduser().resolve()
    receipt_path = runtime_root / "var" / "eira2-private-model-assets.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("private_model_asset_attestation_unreadable") from error
    if not isinstance(receipt, Mapping):
        raise RuntimeError("private_model_asset_attestation_invalid")
    if (
        receipt.get("schema") != _ASSET_SCHEMA
        or receipt.get("ok") is not True
        or receipt.get("all_manifest_referenced_blobs_hash_verified") is not True
        or receipt.get("destination_under_eira2") is not True
        or receipt.get("network_download_performed") is not False
        or tuple(receipt.get("required_models") or ()) != tuple(models)
        or Path(str(receipt.get("destination_root") or "")).resolve() != root
    ):
        raise RuntimeError("private_model_asset_attestation_not_usable_for_boot")

    attested_models = {
        str(row.get("model") or ""): row
        for row in (receipt.get("models") or ())
        if isinstance(row, Mapping)
    }
    unique_blobs: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    for model in models:
        attested = attested_models.get(model)
        if not isinstance(attested, Mapping):
            raise RuntimeError("private_model_boot_attestation_model_missing:" + model)
        manifest = _model_manifest_path(root, model)
        payload = _manifest_payload(manifest, model)
        digests = _manifest_digests(payload, model)
        manifest_sha = _sha256(manifest)
        if manifest_sha != str(attested.get("manifest_sha256") or ""):
            raise RuntimeError("private_model_boot_manifest_changed:" + model)
        if len(digests) != int(attested.get("blob_count") or -1):
            raise RuntimeError("private_model_boot_blob_count_changed:" + model)
        for digest in digests:
            blob = _blob_path(root, digest)
            if not blob.is_file() or blob.is_symlink():
                raise RuntimeError("private_model_boot_blob_missing:" + model + ":" + digest)
            expected_name = "sha256-" + digest.split(":", 1)[1]
            if blob.name != expected_name:
                raise RuntimeError("private_model_boot_blob_path_invalid:" + model + ":" + digest)
            unique_blobs[digest] = blob.stat().st_size
        rows.append({
            "model": model,
            "role": MODEL_ROLES.get(model, "private_candidate"),
            "manifest": str(manifest),
            "manifest_sha256": manifest_sha,
            "blob_count": len(digests),
        })

    if len(unique_blobs) != int(receipt.get("unique_blob_count") or -1):
        raise RuntimeError("private_model_boot_unique_blob_count_changed")
    if sum(unique_blobs.values()) != int(receipt.get("unique_blob_bytes") or -1):
        raise RuntimeError("private_model_boot_unique_blob_bytes_changed")
    return {
        "ok": True,
        "root": str(root),
        "models": rows,
        "model_names": [row["model"] for row in rows],
        "required_models_complete": True,
        "unique_blob_count": len(unique_blobs),
        "unique_blob_bytes": sum(unique_blobs.values()),
        "boot_validation_mode": "prior_full_hash_attestation_plus_current_structure",
        "prior_full_hash_attestation_verified": True,
        "all_manifest_referenced_blobs_hash_reverified_this_boot": False,
    }
'''

def run(cmd,**kw):
 p=subprocess.run(cmd,cwd=str(REPO),text=True,capture_output=True,check=False,**kw)
 if p.returncode: raise RuntimeError('git_failed:'+(' '.join(cmd))+':'+(p.stdout+p.stderr)[-1800:])
 return p.stdout.strip()

def main():
 raw=TARGET.read_bytes(); before=hashlib.sha256(raw).hexdigest()
 if before!=EXPECTED: raise RuntimeError('live_before_hash_mismatch:'+before)
 text=raw.decode('utf-8')
 anchor='\ndef verify_private_model_containment(\n'
 if text.count(anchor)!=1: raise RuntimeError('verify_function_anchor_count')
 text=text.replace(anchor,HELPER+anchor,1)
 old='    verify_model_store(expected_root, models)\n'
 new='    verify_model_store_boot_attested(runtime_root=runtime_root, root=expected_root, models=models)\n'
 if text.count(old)!=1: raise RuntimeError('full_hash_boot_call_anchor_count')
 text=text.replace(old,new,1)
 compile(text,str(TARGET),'exec')
 payload=text.encode(); after=hashlib.sha256(payload).hexdigest()
 parent=run(['git','rev-parse','HEAD'])
 blob=subprocess.run(['git','hash-object','-w','--stdin'],cwd=str(REPO),input=payload,capture_output=True,check=False)
 if blob.returncode: raise RuntimeError('hash_object_failed:'+blob.stderr.decode(errors='replace'))
 blobsha=blob.stdout.decode().strip()
 idx=REPO/'.git'/f'eira2_gen_index_{os.getpid()}'
 env=dict(os.environ); env['GIT_INDEX_FILE']=str(idx)
 try:
  def erun(cmd):
   p=subprocess.run(cmd,cwd=str(REPO),env=env,text=True,capture_output=True,check=False)
   if p.returncode: raise RuntimeError('git_index_failed:'+(' '.join(cmd))+':'+(p.stdout+p.stderr)[-1800:])
   return p.stdout.strip()
  erun(['git','read-tree','HEAD']); erun(['git','update-index','--add','--cacheinfo','100644',blobsha,GEN]); tree=erun(['git','write-tree'])
  commit=run(['git','-c','user.name=EIRA Transport V6','-c','user.email=eira-transport-v6@localhost','commit-tree',tree,'-p',parent,'-m','Generate model fast boot replacement v1'])
 finally:
  idx.unlink(missing_ok=True)
 out={'schema':'eira2_generate_model_fast_boot_replacement_v1','ok':True,'mutates_live':False,'target':'eira2/operations/model_takeover.py','before_sha256':before,'after_sha256':after,'bytes':len(payload),'synthetic_commit':commit,'repo_path':GEN}
 print(json.dumps(out,separators=(',',':'))); return 0
if __name__=='__main__': raise SystemExit(main())
