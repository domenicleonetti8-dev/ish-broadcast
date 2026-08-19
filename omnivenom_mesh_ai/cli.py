from __future__ import annotations
import argparse,json
from .runtime import Omnivenom

def main():
    p=argparse.ArgumentParser();p.add_argument('live');p.add_argument('operation',choices=['refresh','status','find','context']);p.add_argument('query',nargs='?',default='');p.add_argument('--state');p.add_argument('--depth',type=int,default=1);p.add_argument('--limit',type=int,default=20);a=p.parse_args()
    m=Omnivenom(a.live,a.state)
    if a.operation=='refresh':out=m.refresh()
    elif a.operation=='find':out=m.find(a.query,a.limit)
    elif a.operation=='context':out=m.context(a.query,a.depth,a.limit)
    else:out=m.status()
    print(json.dumps(out,indent=2,sort_keys=True,default=str))
if __name__=='__main__':main()
