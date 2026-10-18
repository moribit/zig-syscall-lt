#!/usr/bin/env python3
"""Randomized, paired, independent-process measurements; no strace in timings."""
import argparse, json, os, platform, random, resource, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser()
p.add_argument('--runs',type=int,default=10)
p.add_argument('--iterations',type=int,default=1000)
p.add_argument('--seed',type=int,default=20261019)
p.add_argument('--output',type=Path,default=ROOT/'results'/'fixed')
p.add_argument('--fds',type=int)
p.add_argument('--payload',type=int)
p.add_argument('--ready',type=str,help='comma-separated requested ready percentages')
p.add_argument('--receive-only',action='store_true',help='Measure burst end-to-end and receive intervals')
p.add_argument('--focus',action='store_true',help='Replication: 64/1024/4096 fds, 1/100 percent')
p.add_argument('--binary',default='/tmp/poll-epoll-bench')
a=p.parse_args()
if platform.system()!='Linux': raise SystemExit('Linux is required; use orb -m zig-syscall-lab')
if a.runs<10: raise SystemExit('At least 10 measured repetitions required')
a.output.mkdir(parents=True,exist_ok=True)
if (a.output/'raw.jsonl').exists(): raise SystemExit('Output exists; choose a new directory to preserve raw data')
def cmd(*v): return subprocess.check_output(v,text=True).strip()
if cmd('zig','version')!='0.17.0': raise SystemExit('Zig 0.17.0 required')
subprocess.run(['zig','build-exe',str(ROOT/'main.zig'),'-O','ReleaseFast','-femit-bin='+a.binary],check=True)
conditions=[(n,r,b,m) for n in [64,256,1024,4096] for r in [1,10,50,100] for b in [64,1024] for m in ['readiness','receive']]
if a.fds: conditions=[c for c in conditions if c[0]==a.fds]
if a.payload: conditions=[c for c in conditions if c[2]==a.payload]
if a.ready: conditions=[c for c in conditions if c[1] in [int(v) for v in a.ready.split(',')]]
if not conditions: raise SystemExit('No matching conditions')
if a.receive_only: conditions=[c for c in conditions if c[3]=='receive']
if a.focus: conditions=[c for c in conditions if c[0] in [64,1024,4096] and c[1] in [1,100]]
if resource.getrlimit(resource.RLIMIT_NOFILE)[0] < 2*4096+32: raise SystemExit('RLIMIT_NOFILE too low: need at least 8224')
meta=dict(date=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),uname=cmd('uname','-a'),cpu=cmd('lscpu'),distribution=Path('/etc/os-release').read_text(),zig=cmd('zig','version'),git_sha=cmd('git','rev-parse','HEAD'),git_status=cmd('git','status','--short'),environment='OrbStack Linux VM' if 'orbstack' in cmd('uname','-r') else 'unspecified Linux',fd_limit=resource.getrlimit(resource.RLIMIT_NOFILE),optimization='ReleaseFast',runs=a.runs,warmups=1,seed=a.seed,iterations=a.iterations,consumer_threads=1,includes_producer_timing=True,producer='same-thread burst: producer+receive timed together and separately',event_capacity='N for both backends',read_budget='one payload per ready fd per acquisition',conditions=conditions)
(a.output/'environment.json').write_text(json.dumps(meta,indent=2)+'\n')
rng=random.Random(a.seed)
def measure(c,backend,run,warmup):
 n,ratio,payload,mode=c
 ready=max(1,(n*ratio+50)//100)
 iterations=a.iterations if mode=='readiness' else max(8,min(256,16384//ready))
 seed=a.seed+run*31+n+ratio+payload
 r=subprocess.run([a.binary,backend,mode,str(n),str(ready),str(payload),str(iterations),str(seed)],text=True,capture_output=True,timeout=60)
 if r.returncode: raise RuntimeError(f'{c} {backend}: {r.stderr}')
 row=json.loads(r.stdout)
 row.update(run=run,warmup=warmup,requested_ready_percent=ratio,ready_ratio=ready/n,seed=seed)
 assert row['errors']==0
 assert row['events_observed']==ready*iterations if mode=='readiness' else row['bytes_received']==row['bytes_sent']==ready*payload*iterations
 return row
with (a.output/'raw.jsonl').open('w',buffering=1) as f:
 warmups=conditions.copy(); rng.shuffle(warmups)
 for c in warmups:
  for backend in rng.sample(['poll','epoll'],2): f.write(json.dumps(measure(c,backend,0,True))+'\n')
 jobs=[(c,i) for c in conditions for i in range(1,a.runs+1)]; rng.shuffle(jobs)
 for j,(c,i) in enumerate(jobs):
  # Pair the same condition/seed and randomize backend order within the pair.
  for backend in rng.sample(['poll','epoll'],2): f.write(json.dumps(measure(c,backend,i,False))+'\n')
  if j%40==0: print(f'{j}/{len(jobs)} paired conditions',flush=True)
rows=[json.loads(x) for x in (a.output/'raw.jsonl').read_text().splitlines()]
assert len(rows)==len(conditions)*2*(a.runs+1)
print(f'Saved {len(rows)} rows including warmups to {a.output}')
