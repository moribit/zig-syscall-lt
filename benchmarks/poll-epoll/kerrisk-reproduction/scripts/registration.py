#!/usr/bin/env python3
"""Isolate registration-before-fill vs registration-after-fill using frozen v2 sources."""
import argparse,collections,csv,datetime,difflib,hashlib,json,os,random,statistics,subprocess as sp,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=root/'results/main');out=p.parse_args().output
plan=json.loads((root/'results/registration-plan.json').read_text())
assert json.loads((out/'controls-environment.json').read_text()).get('end_stat'), 'Controls must finish first'
assert not (out/'registration.jsonl').exists(), 'Never overwrite raw data'
assert sp.check_output(['zig','version'],text=True).strip()=='0.17.0'
src=out/'registration-source';src.mkdir();bins=Path('/tmp/kerrisk-registration-bin');bins.mkdir(exist_ok=True)
hashes={};commands=[]
for language,relative in [('c','c/reconstructed.c'),('zig','zig/main.zig')]:
 original=(out/'controls-source-snapshot'/relative).read_text()
 if language=='c':
  start=original.index('  for (int i = 0; i < r; i++) {\n    expected[');end=original.index('  fd_set master',start)
  block=original[start:end];marker='  setup = now() - setup;\n'
 else:
  start=original.index('    for (order[0..r]) |i| {\n        expected[');end=original.index('    var b: Bench',start)
  block=original[start:end];marker='    const setup = now() - setup0;\n'
 for order in plan['orders']:
  text=original if order=='after-fill' else original[:start]+original[end:]
  if order=='before-fill':text=text.replace(marker,marker+block)
  # Capture returned event order outside the timed section (capacity=N here).
  if language=='c':
   text=text.replace('  struct rusage cpu0, cpu1;', '  uint64_t order_hash = 1469598103934665603ULL;\n  for (int j = 0; j < nr; j++) order_hash = (order_hash ^ indices[j]) * 1099511628211ULL;\n  struct rusage cpu0, cpu1;')
   text=text.replace('printf("{\\\"ready_hash\\\":%" PRIu64', 'printf("{\\\"preflight_order_hash\\\":%" PRIu64 ",\\\"ready_hash\\\":%" PRIu64')
   text=text.replace('         ready_hash, duration, setup,', '         order_hash, ready_hash, duration, setup,')
  else:
   text=text.replace('    const cpu0 = cpu();', '    var order_hash: u64 = 1469598103934665603;\n    for (indices[0..nr]) |i| order_hash = (order_hash ^ @as(u64, i)) *% 1099511628211;\n    const cpu0 = cpu();')
   text=text.replace('{{\\\"ready_hash\\\":{d}', '{{\\\"preflight_order_hash\\\":{d},\\\"ready_hash\\\":{d}')
   text=text.replace('.{ ready_hash, duration, setup,', '.{ order_hash, ready_hash, duration, setup,')
  assert 'preflight_order_hash' in text
  target=src/(language+'-'+order+('.c' if language=='c' else '.zig'));target.write_text(text)
  (src/(language+'-'+order+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile=relative,tofile=target.name)))
  binary=bins/(language+'-'+order)
  command=['gcc','-O2','-std=c11','-Wall','-Wextra','-Werror',str(target),'-o',str(binary)] if language=='c' else ['zig','build-exe','-O','ReleaseFast',str(target),'-femit-bin='+str(binary)]
  sp.run(command,check=True);commands.append(command);hashes[target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
conditions=[]
for r in plan['ready']:
 for variant in plan['variants']:
  for order in plan['orders']:conditions.append(dict(variant,ready_fds=r,registration=order))
rng=random.Random(plan['seed_base']);warm=[(0,i,b) for i in range(len(conditions)) for b in plan['languages']];rng.shuffle(warm)
schedule=warm[:]
for run,i in rng.sample([(run,i) for run in range(1,plan['runs']+1) for i in range(len(conditions))],plan['runs']*len(conditions)):
 schedule.extend((run,i,b) for b in rng.sample(plan['languages'],2))
env=dict(date_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),uname=sp.check_output(['uname','-a'],text=True),source_sha256=hashes,build_commands=commands,binary_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in bins.iterdir()},schedule=schedule,plan_sha256=hashlib.sha256((root/'results/registration-plan.json').read_bytes()).hexdigest(),git_sha=sp.check_output(['git','rev-parse','HEAD'],text=True).strip(),affinity=[2],base_environment='controls-environment.json',start_load=Path('/proc/loadavg').read_text())
(out/'registration-environment.json').write_text(json.dumps(env,indent=2)+'\n')
rows=[]
with (out/'registration.jsonl').open('w',buffering=1) as f:
 for seq,(run,i,language) in enumerate(schedule,1):
  c=conditions[i];loops=2000 if run==0 else plan['loops'];seed=plan['seed_base']+run
  command=['taskset','-c','2',str(bins/(language+'-'+c['registration'])),'epoll',c['kind'],'1000',str(c['ready_fds']),str(loops),str(c['timeout']),'1000','random',c['layout'],c['work'],'0',str(seed)]
  start=time.time_ns();child=sp.run(command,text=True,capture_output=True,timeout=120)
  if child.returncode:
   (out/'registration-failure.json').write_text(json.dumps(dict(command=command,stderr=child.stderr,stdout=child.stdout),indent=2));raise SystemExit('Registration experiment failed')
  x=json.loads(child.stdout);assert x['errors']==0 and x['preflight_ready']==c['ready_fds'] and x['events_observed']==loops*c['ready_fds'] and x['wait_calls']==loops
  x.update(c,language=language,condition=i,run=run,warmup=run==0,iterations=loops,seed=seed,sequence=seq,command=command,start_unix_ns=start,end_unix_ns=time.time_ns());f.write(json.dumps(x)+'\n');rows.append(x)
  if run:print(f'registration {seq-len(warm)}/{len(schedule)-len(warm)} {language} {c["label"]} R={c["ready_fds"]} {c["registration"]}',flush=True)
env['end_load']=Path('/proc/loadavg').read_text();env['validated_rows']=len(rows);env['raw_sha256']=hashlib.sha256((out/'registration.jsonl').read_bytes()).hexdigest();(out/'registration-environment.json').write_text(json.dumps(env,indent=2)+'\n')
sp.run(['python3',str(root/'scripts/registration_analysis.py'),str(out)],check=True)
