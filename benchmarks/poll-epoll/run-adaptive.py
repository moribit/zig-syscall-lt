#!/usr/bin/env python3
import argparse, collections, hashlib, json, platform, random, statistics, subprocess, tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(); parser.add_argument('--calibration',type=Path,default=root/'results/crossover-check'); parser.add_argument('--output',type=Path,default=root/'results/adaptive'); args=parser.parse_args()
out=args.output
if platform.system()!='Linux' or subprocess.check_output(['zig','version'],text=True).strip()!='0.17.0': raise SystemExit('Linux / Zig 0.17.0 required')
out.mkdir(parents=True,exist_ok=True)
if (out/'raw.jsonl').exists(): raise SystemExit('Adaptive results already exist; preserve them before rerunning')
# Independent, held-out calibration: only runs 1..5 of crossover-check.
cal=[json.loads(x) for x in (args.calibration/'raw.jsonl').read_text().splitlines()]
costs={(b,r):statistics.median(x['e2e_duration_ns']/x['iterations'] for x in cal if not x['warmup'] and x['run']<=5 and x['backend']==b and x['requested_ready_percent']==r) for b in ['poll','epoll'] for r in [1,100]}
model=dict(fds=4096,payload=1024,ready=[41,4096],poll_ns=[costs['poll',r] for r in [1,100]],epoll_ns=[costs['epoll',r] for r in [1,100]],training='crossover-check runs 1..5 only',training_sha256=hashlib.sha256((args.calibration/'raw.jsonl').read_bytes()).hexdigest(),ema_alpha=.25,minimum_dwell_batches=16,amortization_batches=32,switch_safety_factor=1.1,phase_ms=200)
environment=json.loads((args.calibration/'environment.json').read_text())
environment.update(git_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),git_status=subprocess.check_output(['git','status','--short'],text=True),dynamic_phases='1% -> 100% -> 1%; 200ms each',runs=10,warmups=1)
(out/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
(out/'model.json').write_text(json.dumps(model,indent=2)+'\n')
with tempfile.TemporaryDirectory(prefix='poll-adaptive-') as tmp:
 tmp=Path(tmp); source=tmp/'model.zig'; binary=tmp/'adaptive'
 source.write_text('pub const fds: usize=4096; pub const payload: usize=1024;\n'+''.join(f'pub const {k} = [_]f64{{'+','.join(str(v) for v in model[k])+'};\n' for k in ['ready','poll_ns','epoll_ns']))
 build=['--dep','model','-Mroot='+str(root/'adaptive.zig'),'-Mmodel='+str(source)]
 subprocess.run(['zig','test',*build],check=True)
 subprocess.run(['zig','build-exe','-O','ReleaseFast',*build,'-femit-bin='+str(binary)],check=True)
 rng=random.Random(20261022)
 with (out/'raw.jsonl').open('w',buffering=1) as f:
  for run in range(11):
   for backend in rng.sample(['poll','epoll','adaptive'],3):
    r=subprocess.run([str(binary),backend,'200',str(20261022+run)],text=True,capture_output=True,timeout=30,check=True)
    x=json.loads(r.stdout); x.update(run=run,warmup=run==0,seed=20261022+run)
    assert x['messages']==sum(p['messages'] for p in x['phases'])
    for p in x['phases']: assert p['messages']==p['ready_fds']*p['batches'] and p['bytes']==p['messages']*1024
    f.write(json.dumps(x)+'\n')
   print(f'adaptive experiment {run}/10',flush=True)
