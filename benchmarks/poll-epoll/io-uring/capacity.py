#!/usr/bin/env python3
"""Additional matched control: hold batch=64 and vary SQ only."""
import argparse,csv,datetime,hashlib,json,random,statistics as st,subprocess as sp,time
from pathlib import Path
root=Path(__file__).resolve().parent;plan=json.loads((root/'results/capacity-plan.json').read_text());p=argparse.ArgumentParser();p.add_argument('--analyze-only',action='store_true');p.add_argument('--output',type=Path,default=root/'results/main');args=p.parse_args();out=args.output;env=json.loads((out/'environment.json').read_text());binary=Path(env.get('binary_path','/tmp/zig-uring-bench'))
conditions=[dict(fds=n,ready_fds=(n*pct+99)//100,ready_percent=pct,capacity=cap,batch=64,payload=1024,cq_batch=n) for n in plan['fds'] for pct in plan['ready_percent'] for cap in [64,n]]
if not args.analyze_only:
 assert not (out/'capacity.jsonl').exists()
 env=json.loads((out/'environment.json').read_text());assert hashlib.sha256(binary.read_bytes()).hexdigest()==env['binary_sha256']
 rng=random.Random(plan['ordering_seed']);warm=[(0,i) for i in range(8)];rng.shuffle(warm);schedule=warm[:]
 for run,pair in rng.sample([(run,j) for run in range(1,11) for j in range(4)],40):schedule.extend((run,i) for i in rng.sample([pair*2,pair*2+1],2))
 meta=dict(date_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),base_environment='environment.json',binary_sha256=env['binary_sha256'],plan_sha256=hashlib.sha256((root/'results/capacity-plan.json').read_bytes()).hexdigest(),schedule=schedule,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 with (out/'capacity.jsonl').open('w',buffering=1) as f:
  for sequence,(run,i) in enumerate(schedule,1):
   c=conditions[i];bursts=4 if run==0 else 32;seed=plan['seed_base']+run
   command=['taskset','-c','2',str(binary),'uring',str(c['fds']),str(c['ready_fds']),'1024',str(bursts),str(seed),'64',str(c['capacity']),str(c['cq_batch'])]
   begin=time.time_ns();child=sp.run(command,text=True,capture_output=True,timeout=120)
   if child.returncode:
    (out/'capacity-failure.json').write_text(json.dumps(dict(command=command,stdout=child.stdout,stderr=child.stderr)));raise SystemExit('Control failed')
   x=json.loads(child.stdout);x.update(c,condition=i,bursts=bursts,run=run,warmup=run==0,seed=seed,sequence=sequence,command=command,start_unix_ns=begin,end_unix_ns=time.time_ns());f.write(json.dumps(x)+'\n')
 meta['raw_sha256']=hashlib.sha256((out/'capacity.jsonl').read_bytes()).hexdigest();(out/'capacity-environment.json').write_text(json.dumps(meta,indent=2)+'\n')
rows=[json.loads(s) for s in (out/'capacity.jsonl').read_text().splitlines()];assert len(rows)==88
assert max(x['sequence'] for x in rows if x['warmup'])<min(x['sequence'] for x in rows if not x['warmup'])
summary=[];pairs=[]
def ci(v):
 rng=random.Random(314159);samples=sorted(st.median(rng.choices(v,k=len(v))) for _ in range(10000));return samples[250],samples[9749]
for i,c in enumerate(conditions):
 g=[x for x in rows if x['condition']==i];assert len(g)==11 and {x['run'] for x in g}==set(range(11))
 for x in g:
  assert all(x[k]==v for k,v in c.items()) and x['errors']==0 and x['messages']==x['ready_fds']*x['bursts'] and x['bytes_sent']==x['bytes_received']==x['messages']*1024
 g=[x for x in g if not x['warmup']];rate=[x['messages']*1e9/x['e2e_ns'] for x in g];lo,hi=ci(rate)
 summary.append(dict(c,n=10,msg_s_median=st.median(rate),ci95_low=lo,ci95_high=hi,enter_calls_median=st.median(x['enter_calls'] for x in g),initial_enter_calls_median=st.median(x['initial_enter_calls'] for x in g),cpu_us_median=st.median(x['user_us']+x['system_us'] for x in g)))
for j in range(4):
 left={x['run']:x for x in rows if x['condition']==j*2 and not x['warmup']};right={x['run']:x for x in rows if x['condition']==j*2+1 and not x['warmup']};ratios=[]
 for run,x in left.items():
  y=right[run];assert x['seed']==y['seed'] and x['messages']==y['messages'] and x['bytes_received']==y['bytes_received'];ratios.append(y['e2e_ns']/x['e2e_ns'])
 lo,hi=ci(ratios);pairs.append(dict(fds=left[1]['fds'],ready_fds=left[1]['ready_fds'],sq64_over_sqN_speed=st.median(ratios),ci95_low=lo,ci95_high=hi,n=10))
for name,data in [('capacity-summary',summary),('capacity-paired',pairs)]:
 with (out/(name+'.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)
print('Validated 80 matched SQ-capacity controls and 8 warmups.')
