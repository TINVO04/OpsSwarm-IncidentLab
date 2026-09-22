#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean
fs=sorted(Path('evidence/campaign').glob('campaign-*.json'))
if not fs: raise SystemExit('run campaign first')
d=json.loads(fs[-1].read_text()); rows=d['results']; out={}
for arm in sorted(set(x['arm'] for x in rows)):
    a=[x for x in rows if x['arm']==arm]; out[arm]={'runs':len(a),'mean_elapsed_s':mean(x['elapsed_s'] for x in a),'verified_rate':sum(bool(x['verified']) for x in a)/len(a),'resolved_rate':sum(x['status']=='RESOLVED' for x in a)/len(a)}
r={'warning':'B0 is scripted software baseline; do not interpret as human MTTA/MTTR','summary':out}; p=Path('evidence/reports');p.mkdir(parents=True,exist_ok=True); (p/'latest-summary.json').write_text(json.dumps(r,indent=2)); print(json.dumps(r,indent=2))
