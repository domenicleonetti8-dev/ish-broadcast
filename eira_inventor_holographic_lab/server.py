from __future__ import annotations
import argparse,json,mimetypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parent; ARCHIVE=ROOT/"archive"; JOBS=ARCHIVE/"jobs"; JOBS.mkdir(parents=True,exist_ok=True)
class H(BaseHTTPRequestHandler):
 def sendj(self,c,o):
  b=json.dumps(o).encode(); self.send_response(c); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  p=urlparse(self.path).path
  if p=="/health": return self.sendj(200,{"ok":True,"service":"eira-inventor-v5"})
  if p.startswith("/api/jobs/"):
   q=JOBS/(p.rsplit('/',1)[-1]+".json"); return self.sendj(200,json.loads(q.read_text()) if q.exists() else {"error":"not_found"})
  f=ROOT/"static"/("index.html" if p=="/" else p.lstrip('/'))
  if f.is_file():
   b=f.read_bytes(); self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(f.name)[0] or "application/octet-stream"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
  self.sendj(404,{"error":"not_found"})
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--host",default="0.0.0.0"); ap.add_argument("--port",type=int,default=8787); a=ap.parse_args(); ThreadingHTTPServer((a.host,a.port),H).serve_forever()
if __name__=="__main__": main()
