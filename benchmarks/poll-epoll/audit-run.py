#!/usr/bin/env python3
"""Frozen additional experiments. Refuses overwrites; historical model is unchanged."""
import argparse, shutil, json, subprocess as sp, random, time, hashlib, os, platform
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,default=root/'results/audit-v2');args=parser.parse_args();out=args.output
out.mkdir(parents=True,exist_ok=True)
if platform.system()!='Linux': raise SystemExit('Linux required')
if (out/'probe.jsonl').exists(): raise SystemExit('results exist; use a new output directory')
if not (out/'historical-manifest.json').exists():
 (out/'historical-manifest.json').write_text(json.dumps({str(p.relative_to(root/'results')):hashlib.sha256(p.read_bytes()).hexdigest() for name in ['fixed','replication','end-to-end','end-to-end-replication','crossover-check','adaptive'] for p in (root/'results'/name).glob('*') if p.is_file()},indent=2)+'\n')
snapshot=out/'source-snapshot';snapshot.mkdir(exist_ok=True)
for source in root.glob('*.zig'):shutil.copy2(source,snapshot/source.name)
model=json.loads((root/'results/adaptive/model.json').read_text())
Path('/tmp/audit-model.zig').write_text('pub const fds: usize=4096; pub const payload: usize=1024;\n'+''.join('pub const '+k+' = [_]f64{'+','.join(map(str,model[k]))+'};\n' for k in ['ready','poll_ns','epoll_ns']))
shutil.copy2('/tmp/audit-model.zig',snapshot/'model.zig')
for src,bin in [('main.zig','poll-audit'),('probe.zig','poll-probe')]:
 sp.run(['zig','build-exe','-O','ReleaseFast',str(root/src),'-femit-bin=/tmp/'+bin],check=True)
build=['--dep','model','-Mroot='+str(root/'adaptive.zig'),'-Mmodel=/tmp/audit-model.zig']
sp.run(['zig','test',*build],check=True)
sp.run(['zig','build-exe','-O','ReleaseFast',*build,'-femit-bin=/tmp/adaptive-audit'],check=True)
def cmd(*a): return sp.check_output(a,text=True).strip()
env=dict(uname=cmd('uname','-a'),cpu=cmd('lscpu'),os=Path('/etc/os-release').read_text(),zig=cmd('zig','version'),git_sha=cmd('git','rev-parse','HEAD'),git_status=cmd('git','status','--short'),affinity=sorted(os.sched_getaffinity(0)),measurement_cpu=2,optimization='ReleaseFast',vm='OrbStack',fd_limit=cmd('sh','-c','ulimit -n'),model_sha256=hashlib.sha256((root/'results/adaptive/model.json').read_bytes()).hexdigest(),sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.zig')},start_load=Path('/proc/loadavg').read_text(),start_stat=Path('/proc/stat').read_text(),schedule_seed=20261023,dynamic_warmup_order='all nine warmups precede every measured dynamic run',binaries={b:hashlib.sha256(Path('/tmp',b).read_bytes()).hexdigest() for b in ['poll-audit','poll-probe','adaptive-audit']})
(out/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
rng=random.Random(20261023); seq=0
def execute(binary,args,pinned=True):
 global seq
 seq+=1; start=time.time_ns()
 lines=sp.check_output((['taskset','-c','2'] if pinned else [])+[binary,*map(str,args)],text=True,timeout=45).splitlines()
 x=json.loads(lines[0]); x.update(sequence=seq,start_unix_ns=start,end_unix_ns=time.time_ns(),pinned=pinned)
 return x,[json.loads(l) for l in lines[1:]]
with (out/'probe.jsonl').open('w',buffering=1) as f:
 for run in range(21):
  jobs=[(n,r,b,m) for n,r in [(1024,10),(1024,1024),(4096,41),(4096,4096)] for b in ['poll','epoll'] for m in ['combined','syscall','scan','validate','clocks']];rng.shuffle(jobs)
  for n,r,b,m in jobs:
   x,_=execute('/tmp/poll-probe',[b,m,n,r,2000,20261023+run]);x.update(run=run,warmup=run==0,seed=20261023+run);f.write(json.dumps(x)+'\n')
 print('probe complete',flush=True)
with (out/'controls.jsonl').open('w',buffering=1) as f:
 for run in range(31):
  jobs=[(r,b,order) for r in [41,4096] for b in ['poll','epoll','poll-watched'] for order in ['shuffled','ascending']];rng.shuffle(jobs)
  for r,b,order in jobs:
   args=[b,'receive',4096,r,1024,64,20261024+run]+(['ascending'] if order=='ascending' else [])
   x,_=execute('/tmp/poll-audit',args);x.update(run=run,warmup=run==0,seed=20261024+run,order=order);f.write(json.dumps(x)+'\n')
  print('controls',run,flush=True)
with (out/'replication.jsonl').open('w',buffering=1) as f:
 for run in range(31):
  for b in rng.sample(['poll','epoll'],2):
   x,_=execute('/tmp/poll-audit',[b,'receive',4096,4096,1024,64,20261025+run],False);x.update(run=run,warmup=run==0,seed=20261025+run);f.write(json.dumps(x)+'\n')
 print('unpinned replication complete',flush=True)
with (out/'dynamic-warmed.jsonl').open('w',buffering=1) as f:
 warm=[(0,high) for high in [200,1000,5000]];rng.shuffle(warm)
 jobs=[(run,high) for run in range(1,11) for high in [200,1000,5000]];rng.shuffle(jobs);jobs=warm+jobs
 for run,high in jobs:
  for b in rng.sample(['poll','epoll','adaptive'],3):
   x,_=execute('/tmp/adaptive-audit',[b,200,20261026+run,high]);x.update(run=run,warmup=run==0,seed=20261026+run,high_ms=high,diagnostic=False);f.write(json.dumps(x)+'\n')
  print('dynamic',run,high,flush=True)
with (out/'diagnostics.jsonl').open('w') as f:
 for high in [200,1000,5000]:
  x,rows=execute('/tmp/adaptive-audit',['adaptive',200,20261101,high,'diagnostic']);x.update(high_ms=high,diagnostic=True,seed=20261101);f.write(json.dumps(x)+'\n')
  for row in rows: row.update(high_ms=high);f.write(json.dumps(row)+'\n')
env.update(end_load=Path('/proc/loadavg').read_text(),end_stat=Path('/proc/stat').read_text())
(out/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
