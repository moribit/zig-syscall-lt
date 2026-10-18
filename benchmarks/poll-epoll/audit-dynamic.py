#!/usr/bin/env python3
"""Warm all dynamic conditions first; preserve the interleaved initial series."""
import argparse,hashlib,json,random,subprocess as sp,time
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=root/'results/audit-v2');parser.add_argument('--binary',default='/tmp/adaptive-audit-final');args=parser.parse_args();out=args.output
path=out/'dynamic-warmed.jsonl'
if path.exists():raise SystemExit('dynamic-warmed exists; do not overwrite')
rng=random.Random(20261104);seq=0
warm=[(0,h,b) for h in [200,1000,5000] for b in ['poll','epoll','adaptive']];rng.shuffle(warm)
jobs=[]
for run,high in rng.sample([(r,h) for r in range(1,11) for h in [200,1000,5000]],30):
 jobs.extend((run,high,b) for b in rng.sample(['poll','epoll','adaptive'],3))
env=dict(schedule_seed=20261104,workload_seed_base=20261026,start_stat=Path('/proc/stat').read_text(),start_load=Path('/proc/loadavg').read_text(),binary_sha256=hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),source_sha256=hashlib.sha256((root/'adaptive.zig').read_bytes()).hexdigest(),model_sha256=hashlib.sha256((root/'results/adaptive/model.json').read_bytes()).hexdigest(),warmup_order='All nine warmups before any measured run',reason='Initial series shuffled run=0 together with measured runs; preserve it but correct the warmup protocol. No model tuning.')
with path.open('w',buffering=1) as f:
 for run,high,b in warm+jobs:
  seq+=1;t=time.time_ns();command=['taskset','-c','2',args.binary,b,'200',str(20261026+run),str(high)]
  x=json.loads(sp.check_output(command,text=True,timeout=30));x.update(run=run,warmup=run==0,seed=20261026+run,high_ms=high,diagnostic=False,pinned=True,sequence=seq,start_unix_ns=t,end_unix_ns=time.time_ns(),loadavg=Path('/proc/loadavg').read_text())
  f.write(json.dumps(x)+'\n')
  if seq%9==0:print('warm-first dynamic',seq,'/99',flush=True)
env.update(end_stat=Path('/proc/stat').read_text(),end_load=Path('/proc/loadavg').read_text())
(out/'dynamic-warmed-environment.json').write_text(json.dumps(env,indent=2)+'\n')
