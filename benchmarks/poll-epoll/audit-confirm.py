#!/usr/bin/env python3
"""Second pinned seed series after analysis/rendering, to check interference sensitivity."""
import argparse,hashlib,json,random,subprocess as sp,time
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=root/'results/audit-v2');parser.add_argument('--binary',default='/tmp/poll-audit');args=parser.parse_args();out=args.output
if (out/'confirmation.jsonl').exists():raise SystemExit('confirmation exists; do not overwrite')
rng=random.Random(20261103);start=Path('/proc/stat').read_text();load=Path('/proc/loadavg').read_text();seq=0
with (out/'confirmation.jsonl').open('w',buffering=1) as f:
 for run in range(31):
  jobs=[(b,order) for b in ['poll','epoll'] for order in ['shuffled','ascending']];rng.shuffle(jobs)
  for b,order in jobs:
   command=['taskset','-c','2',args.binary,b,'receive','4096','4096','1024','64',str(20261103+run)]+(['ascending'] if order=='ascending' else [])
   seq+=1;t=time.time_ns();load_before=Path('/proc/loadavg').read_text()
   x=json.loads(sp.check_output(command,text=True,timeout=30));x.update(run=run,seed=20261103+run,order=order,warmup=run==0,pinned=True,start_unix_ns=t,end_unix_ns=time.time_ns(),sequence=seq,loadavg=load_before)
   f.write(json.dumps(x)+'\n')
(out/'confirmation-environment.json').write_text(json.dumps(dict(start_stat=start,start_load=load,end_stat=Path('/proc/stat').read_text(),end_load=Path('/proc/loadavg').read_text(),purpose='Second seed series after analysis/rendering; no concurrent agent workload in this VM',binary=args.binary,binary_sha256=hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),schedule_seed=20261103),indent=2)+'\n')
print('confirmation 120 measurements + 4 warmups complete')
