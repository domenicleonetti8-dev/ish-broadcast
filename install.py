from __future__ import annotations
import argparse,hashlib,py_compile,shutil,time
from pathlib import Path
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--live-root',default='/media/domenicleonetti/easystore/EIRA/LIVE'); a=ap.parse_args(); live=Path(a.live_root).resolve(); target=live/'extensions/eira_inventor_holographic_lab'; src=Path(__file__).resolve().parent/'eira_inventor_holographic_lab'
 if not src.is_dir(): raise SystemExit('STOP: source extension missing')
 mainpy=live/'main.py'; before=hashlib.sha256(mainpy.read_bytes()).hexdigest() if mainpy.exists() else None; stamp=time.strftime('%Y%m%d_%H%M%S'); backup=target.with_name(target.name+'.bak_v5_'+stamp); archive_tmp=None
 if target.exists():
  if (target/'archive').exists(): archive_tmp=live/f'.eira_inventor_archive_{stamp}'; shutil.copytree(target/'archive',archive_tmp)
  shutil.copytree(target,backup); shutil.rmtree(target)
 shutil.copytree(src,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc','archive'))
 if archive_tmp and archive_tmp.exists(): shutil.copytree(archive_tmp,target/'archive'); shutil.rmtree(archive_tmp)
 for p in target.rglob('*.py'): py_compile.compile(str(p),doraise=True)
 after=hashlib.sha256(mainpy.read_bytes()).hexdigest() if mainpy.exists() else None
 if before!=after:
  if target.exists(): shutil.rmtree(target)
  if backup.exists(): shutil.copytree(backup,target)
  raise SystemExit('STOP: main.py changed; rollback completed')
 print('EIRA INVENTOR HOLOGRAPHIC LAB V5 INSTALL: PASS'); print('TARGET:',target); print('BACKUP:',backup if backup.exists() else 'fresh install'); print('ARCHIVE: preserved' if archive_tmp is not None else 'ARCHIVE: fresh')
if __name__=='__main__': main()
