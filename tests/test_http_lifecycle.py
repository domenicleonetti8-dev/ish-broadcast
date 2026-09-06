import os,sys,time,base64,json,tempfile,threading,urllib.request
from pathlib import Path
os.environ['EIRA_INVENTOR_TEST_MODE']='1'; os.environ['EIRA_INVENTOR_ARCHIVE']=tempfile.mkdtemp(prefix='eira_inv_test_'); sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eira_inventor_holographic_lab.server import H
from http.server import ThreadingHTTPServer
srv=ThreadingHTTPServer(('127.0.0.1',0),H); port=srv.server_address[1]; threading.Thread(target=srv.serve_forever,daemon=True).start()
def post(p,o):
 q=urllib.request.Request(f'http://127.0.0.1:{port}{p}',data=json.dumps(o).encode(),headers={'Content-Type':'application/json'}); return json.load(urllib.request.urlopen(q))
def get(p): return json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}{p}'))
inv=post('/api/inventions',{'title':'Lifecycle Test','description':'multi-view invention evidence'})
for name,data in [('front.jpg',b'front'),('rear.png',b'rear')]:
 post('/api/upload',{'invention_id':inv['id'],'name':name,'mime':'image/jpeg' if name.endswith('.jpg') else 'image/png','data_base64':base64.b64encode(data).decode()})
j=post('/api/render',{'invention_id':inv['id']})
for _ in range(50):
 q=get('/api/jobs/'+j['job_id'])
 if q['status'] in ('completed','failed','cancelled'): break
 time.sleep(.1)
health=get('/health')
assert q['status']=='completed',q
assert q['model_url'],q
assert q.get('source_image_count')==2,q
assert health['ok'] and health['multi_photo'] and health['forensic_blueprints'] and health['apple_ar_usdz'],health
print('HTTP MULTI-PHOTO LIFECYCLE PASS',q['status'],q['source_image_count'],q['model_url']); srv.shutdown()
