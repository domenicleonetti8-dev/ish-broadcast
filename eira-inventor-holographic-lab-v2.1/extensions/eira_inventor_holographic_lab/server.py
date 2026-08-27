from __future__ import annotations
import argparse, base64, json, mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote
from . import plugin

ROOT=Path(__file__).resolve().parent
STATIC=ROOT/"static"

class Handler(BaseHTTPRequestHandler):
    server_version="EIRA-InventorLab/1.0"
    def log_message(self, fmt, *args): pass
    def send_bytes(self, code, data, ctype="application/octet-stream"):
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(data)
    def send_json(self, code, obj):
        self.send_bytes(code,json.dumps(obj,default=str).encode("utf-8"),"application/json; charset=utf-8")
    def body_json(self):
        n=int(self.headers.get("Content-Length","0") or "0")
        if n>50_000_000: raise ValueError("request_too_large")
        return json.loads(self.rfile.read(n) or b"{}")
    def do_GET(self):
        p=urlparse(self.path).path
        try:
            if p=="/api/status": return self.send_json(200,plugin.status())
            if p=="/api/engineering3d": return self.send_json(200,plugin.engineering3d_status())
            if p=="/api/inventions": return self.send_json(200,plugin.list_inventions())
            if p.startswith("/api/inventions/"):
                return self.send_json(200,plugin.get_invention(unquote(p.rsplit("/",1)[-1])))
            if p.startswith("/archive/"):
                rel=Path(unquote(p[len("/archive/"):]))
                target=(plugin.DATA_ROOT/rel).resolve()
                if plugin.DATA_ROOT not in target.parents and target!=plugin.DATA_ROOT: raise PermissionError("unsafe_path")
                if not target.is_file(): return self.send_json(404,{"error":"not_found"})
                return self.send_bytes(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            target=STATIC/("index.html" if p in ("/","") else p.lstrip("/"))
            target=target.resolve()
            if STATIC not in target.parents and target!=STATIC: raise PermissionError("unsafe_path")
            if not target.is_file(): return self.send_json(404,{"error":"not_found"})
            return self.send_bytes(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or "text/plain")
        except Exception as exc: return self.send_json(500,{"error":f"{type(exc).__name__}:{exc}"})
    def do_POST(self):
        p=urlparse(self.path).path
        try:
            obj=self.body_json()
            if p=="/api/inventions": return self.send_json(201,plugin.create_invention(obj.get("title",""),obj.get("description","")))
            if p=="/api/upload":
                raw=base64.b64decode(obj.get("data_base64",""),validate=True)
                return self.send_json(201,plugin.add_asset(obj["invention_id"],obj.get("name","asset.bin"),obj.get("mime","application/octet-stream"),raw,obj.get("kind","source")))
            if p=="/api/render": return self.send_json(202,plugin.queue_render(obj["invention_id"],obj.get("mode","engineering_completion")))
            if p=="/api/render/process": return self.send_json(200,plugin.process_next_render())
            if p=="/api/note": return self.send_json(201,plugin.add_note(obj["invention_id"],obj.get("category","note"),obj.get("text",""),obj.get("confidence"),obj.get("source","user")))
            if p=="/api/chat": return self.send_json(200,plugin.chat(obj.get("message","")))
            return self.send_json(404,{"error":"not_found"})
        except (ValueError,KeyError) as exc: return self.send_json(400,{"error":str(exc)})
        except Exception as exc: return self.send_json(500,{"error":f"{type(exc).__name__}:{exc}"})

def run(host="127.0.0.1",port=8787):
    httpd=ThreadingHTTPServer((host,int(port)),Handler)
    print(f"EIRA_INVENTOR_LAB=http://{host}:{port}")
    httpd.serve_forever()

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--host",default="127.0.0.1"); ap.add_argument("--port",type=int,default=8787)
    a=ap.parse_args(); run(a.host,a.port)
