#!/usr/bin/env python3
import argparse,requests,time,json
from pathlib import Path

def post(u):
    r=requests.post(u,timeout=15); r.raise_for_status(); return r.json()
def one(base,c,arm):
    t=time.perf_counter(); post(base+'/lab/reset'); post(base+'/lab/fault/'+c); d=post(base+'/lab/detect')
    if not d['created']: return {'arm':arm,'scenario':c,'elapsed_s':time.perf_counter()-t,'status':'NO_INCIDENT','verified':False}
    i=d['created'][0]['id']; f=post(base+'/lab/approve/'+i)
    return {'arm':arm,'scenario':c,'incident_id':i,'elapsed_s':time.perf_counter()-t,'status':f['status'],'verified':f.get('recovery',{}).get('verification',{}).get('verified',False)}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',default='http://localhost:8080'); ap.add_argument('--scenarios',nargs='+',default=['C01','C02','C03','C06','C09','C12']); ap.add_argument('--repetitions',type=int,default=3); a=ap.parse_args(); rows=[]
    for c in a.scenarios:
        for r in range(a.repetitions):
            rows.append(one(a.base_url,c,'B0_SCRIPTED_PROCEDURAL')|{'rep':r+1,'warning':'not human baseline'})
            rows.append(one(a.base_url,c,'M1_OPSSWARM')|{'rep':r+1})
            print(c,r+1)
    p=Path('evidence/campaign');p.mkdir(parents=True,exist_ok=True); fn=p/f'campaign-{int(time.time())}.json'; fn.write_text(json.dumps({'warning':'B0 is scripted software baseline, not human MTTR','results':rows},indent=2)); print(fn)
if __name__=='__main__': main()
